// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Decisions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Provides an <see cref="IChatClient"/> for Jev, the TypeSafe System One model, which answers typed questions about
/// a conversation instead of writing text.
/// </summary>
/// <remarks>
/// <para>
/// Each request sends the conversation as the Jev state, together with the questions passed with
/// <see cref="JevChatOptionsExtensions.WithJevQuestions"/> (or <see cref="JevChatClientOptions.DefaultQuestions"/>).
/// The response text is the <see cref="JevResult"/> as JSON, and <see cref="JevResultExtensions.GetJevResult(ChatResponse)"/>
/// returns it typed. This follows the TypeSafe connector for Python, so both languages behave alike.
/// </para>
/// <para>
/// Jev can also call function tools whose arguments come from a closed set: constants, enums, Booleans, and arrays of
/// enum values. The client adds internal questions that choose the tool and its arguments, and returns a
/// <see cref="FunctionCallContent"/> for a function-invoking client (which a <c>ChatClientAgent</c> adds) to run.
/// Once the turn has used <see cref="JevChatClientOptions.MaximumToolCallsPerTurn"/> calls, the client answers the
/// questions instead; the response text is then the tool results followed by one <c>id: answer</c> line per Choice
/// and Score answer. Tools with free-form arguments, such as text or numbers, are left out with a warning.
/// </para>
/// <para>
/// Features that need generated text fail with <see cref="NotSupportedException"/>: streaming, sampling and output
/// options such as <see cref="ChatOptions.Temperature"/> or a JSON <see cref="ChatOptions.ResponseFormat"/>,
/// server-side conversations and background responses, tools other than functions, and content other than text,
/// reasoning text, and function calls and results. Tool approval requests and responses are left out of the state,
/// because the call and result they lead to carry the information.
/// </para>
/// </remarks>
public sealed class JevChatClient : IChatClient
{
    private readonly JevHttpClient _client;
    private readonly DecisionChatEngine _engine;
    private readonly IReadOnlyDictionary<string, JevQuestion>? _defaultQuestions;
    private readonly ChatClientMetadata _metadata;

    /// <summary>
    /// Initializes a new instance of the <see cref="JevChatClient"/> class.
    /// </summary>
    /// <param name="credential">The TypeSafe API key, sent as a bearer token.</param>
    /// <param name="options">The client and pipeline options. Defaults are used when <see langword="null"/>.</param>
    /// <exception cref="ArgumentException">
    /// <see cref="JevChatClientOptions.ModelId"/> is empty, or <see cref="JevChatClientOptions.Endpoint"/> is not an
    /// absolute URI.
    /// </exception>
    public JevChatClient(ApiKeyCredential credential, JevChatClientOptions? options = null)
    {
        _ = Throw.IfNull(credential);
        options ??= new JevChatClientOptions();

        if (string.IsNullOrWhiteSpace(options.ModelId))
        {
            Throw.ArgumentException(nameof(options), $"{nameof(JevChatClientOptions)}.{nameof(JevChatClientOptions.ModelId)} must not be empty.");
        }

        if (options.Endpoint?.IsAbsoluteUri is false)
        {
            Throw.ArgumentException(nameof(options), $"{nameof(JevChatClientOptions)}.{nameof(JevChatClientOptions.Endpoint)} must be an absolute URI.");
        }

        // The questions are copied so that later changes to the caller's dictionary do not change this client.
        this._defaultQuestions = options.DefaultQuestions?.ToDictionary(question => question.Key, question => question.Value, StringComparer.Ordinal);
        this._client = new JevHttpClient(credential, options, options.Endpoint, options.ModelId);
        this._metadata = new ChatClientMetadata(JevDecisionClient.ProviderName, this._client.Endpoint, this._client.ModelId);

        // The conversation, tool calling, and turn logic are provider-neutral; this client supplies Jev as the decision
        // client and keeps the Jev result as what callers see.
        this._engine = new DecisionChatEngine(new JevDecisionClient(this._client), new DecisionChatEngineOptions
        {
            ModelName = "Jev",
            QuestionsDescription = $"the questions passed with {nameof(JevChatOptionsExtensions.WithJevQuestions)}",
            CallIdPrefix = "typesafe",
            DescribeAnswers = DescribeAnswers,
            MaximumToolCallsPerTurn = options.MaximumToolCallsPerTurn,
            Logger = (options.ClientLoggingOptions?.LoggerFactory ?? NullLoggerFactory.Instance).CreateLogger<JevChatClient>(),
        });
    }

    /// <inheritdoc />
    /// <exception cref="InvalidOperationException">
    /// The request has no questions, a required tool call is impossible, or the Jev result does not answer every
    /// question.
    /// </exception>
    /// <exception cref="NotSupportedException">The request uses an option, tool, or content that Jev does not support.</exception>
    /// <exception cref="ClientResultException">The TypeSafe API rejected the request.</exception>
    public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // The Jev questions are sent unchanged, so JSON instructions and criteria keep their form; the decision
        // questions made from them correlate the answers.
        IReadOnlyDictionary<string, JevQuestion> questions = this.GetQuestions(options);
        JevContractValidator.ValidateQuestions(questions, nameof(options));
        List<DecisionQuestion> decisionQuestions = [.. questions.Select(question => JevDecisionMapping.ToDecisionQuestion(question.Key, question.Value))];
        var decisionOptions = new DecisionOptions
        {
            ModelId = options?.ModelId,
            RawRepresentationFactory = _ => new JevDecisionRequestOptions { Questions = questions },
        };

        return await this._engine.GetResponseAsync(messages, options, decisionQuestions, decisionOptions, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    /// <exception cref="NotSupportedException">Always: Jev answers all questions at once and does not stream.</exception>
    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException($"Jev answers all questions at once and does not stream. Call {nameof(GetResponseAsync)}, or RunAsync on an agent.");

    /// <inheritdoc />
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is not null ? null
            : serviceType == typeof(ChatClientMetadata) ? this._metadata
            : serviceType.IsInstanceOfType(this) ? this
            : null;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        // The pipeline owns no disposable resources; its default transport shares one HttpClient per process.
    }

    /// <summary>
    /// Describes the answers to the caller's questions as the <see cref="JevResult"/> that callers read, in JSON for the
    /// response text and typed for <see cref="JevResultExtensions.GetJevResult(ChatResponse)"/>.
    /// </summary>
    private static DecisionChatAnswers DescribeAnswers(DecisionResponse answers)
    {
        JevResult result = JevDecisionMapping.ToJevResult(answers);
        return new DecisionChatAnswers(JsonSerializer.Serialize(result, JevJsonContext.Default.JevResult), result);
    }

    private IReadOnlyDictionary<string, JevQuestion> GetQuestions(ChatOptions? options)
    {
        IReadOnlyDictionary<string, JevQuestion>? questions =
            (options?.RawRepresentationFactory?.Invoke(this) as JevChatRequestOptions)?.Questions ?? this._defaultQuestions;
        if (questions is null)
        {
            Throw.InvalidOperationException(
                $"Jev needs questions to answer. Pass them with {nameof(ChatOptions)}.{nameof(JevChatOptionsExtensions.WithJevQuestions)}, or set {nameof(JevChatClientOptions)}.{nameof(JevChatClientOptions.DefaultQuestions)}.");
        }

        if (questions.Count == 0)
        {
            Throw.ArgumentException(nameof(options), "Jev needs at least one question.");
        }

        return questions;
    }
}
