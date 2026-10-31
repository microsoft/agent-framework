// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
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
    private const string ProviderName = "typesafe.ai";

    private readonly JevHttpClient _client;
    private readonly IReadOnlyDictionary<string, JevQuestion>? _defaultQuestions;
    private readonly int _maximumToolCallsPerTurn;
    private readonly ILogger _logger;
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
        this._maximumToolCallsPerTurn = options.MaximumToolCallsPerTurn;
        this._logger = (options.ClientLoggingOptions?.LoggerFactory ?? NullLoggerFactory.Instance).CreateLogger<JevChatClient>();
        this._client = new JevHttpClient(credential, options, options.Endpoint, options.ModelId);
        this._metadata = new ChatClientMetadata(ProviderName, this._client.Endpoint, this._client.ModelId);
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
        IReadOnlyList<ChatMessage> history = messages as IReadOnlyList<ChatMessage> ?? [.. messages];

        EnsureSupported(options);
        IReadOnlyDictionary<string, JevQuestion> questions = this.GetQuestions(options);
        JevToolCallCompiler.EnsureNoReservedQuestionIds(questions.Keys);
        List<AIFunctionDeclaration> tools = GetFunctionTools(options);

        // Once the turn has used its tool calls, tools are no longer offered, so the next response answers the
        // questions with the tool results in the state. This is what ends the function-invoking loop, like the
        // max_function_calls default of one in the Python connector.
        int turnStart = JevChatState.GetCurrentTurnStart(history);
        ChatToolMode? toolMode = JevChatState.CountCurrentTurnCalls(history, turnStart) >= this._maximumToolCallsPerTurn
            ? ChatToolMode.None
            : options?.ToolMode;
        JevToolCallPlan? plan = JevToolCallCompiler.Compile(tools, toolMode, JevChatState.GetCurrentTurnCalls(history, turnStart), this._logger);

        var allQuestions = new Dictionary<string, JevQuestion>(StringComparer.Ordinal);
        foreach (KeyValuePair<string, JevQuestion> question in questions)
        {
            allQuestions[question.Key] = question.Value;
        }

        foreach (KeyValuePair<string, JevQuestion> question in plan?.Questions ?? new Dictionary<string, JevQuestion>())
        {
            allQuestions[question.Key] = question.Value;
        }

        var request = new JevRequest { State = JevChatState.Build(history, options?.Instructions), Questions = allQuestions };
        JevContractValidator.ValidateRequest(request);

        string modelId = string.IsNullOrWhiteSpace(options?.ModelId) ? this._client.ModelId : options!.ModelId!;
        JevResult result = await this._client.SystemOneAsync(request, modelId, cancellationToken).ConfigureAwait(false);

        // Validation covers the internal questions too, so the decoders below only see labels they offered.
        JevContractValidator.ValidateResult(request, result);
        UsageDetails? usage = result.Usage is { } tokens
            ? new UsageDetails { InputTokenCount = tokens.InputTokens, OutputTokenCount = tokens.OutputTokens, TotalTokenCount = tokens.InputTokens + tokens.OutputTokens }
            : null;

        if (plan?.Decode(result) is { } call)
        {
            var callMessage = new ChatMessage(ChatRole.Assistant, [new FunctionCallContent($"typesafe-{Guid.NewGuid():N}", call.Function.Name, call.Arguments)]);
            return new ChatResponse(callMessage)
            {
                ModelId = result.Model,
                FinishReason = ChatFinishReason.ToolCalls,
                Usage = usage,
                CreatedAt = DateTimeOffset.UtcNow,
            };
        }

        // The caller asked only its own questions, so the internal tool answers are removed from what it sees.
        JevResult answers = WithoutInternalAnswers(result, questions);
        var message = new ChatMessage(ChatRole.Assistant, BuildText(history, turnStart, answers)) { RawRepresentation = answers };
        return new ChatResponse(message)
        {
            ModelId = result.Model,
            FinishReason = ChatFinishReason.Stop,
            Usage = usage,
            CreatedAt = DateTimeOffset.UtcNow,
            RawRepresentation = answers,
        };
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

    private static void EnsureSupported(ChatOptions? options)
    {
        if (options is null)
        {
            return;
        }

        var unsupported = new List<string>();
        AddIf(options.Temperature is not null, nameof(ChatOptions.Temperature));
        AddIf(options.TopP is not null, nameof(ChatOptions.TopP));
        AddIf(options.TopK is not null, nameof(ChatOptions.TopK));
        AddIf(options.MaxOutputTokens is not null, nameof(ChatOptions.MaxOutputTokens));
        AddIf(options.FrequencyPenalty is not null, nameof(ChatOptions.FrequencyPenalty));
        AddIf(options.PresencePenalty is not null, nameof(ChatOptions.PresencePenalty));
        AddIf(options.Seed is not null, nameof(ChatOptions.Seed));
        AddIf(options.Reasoning is not null, nameof(ChatOptions.Reasoning));
        AddIf(options.StopSequences is { Count: > 0 }, nameof(ChatOptions.StopSequences));
        AddIf(options.ResponseFormat is not (null or ChatResponseFormatText), nameof(ChatOptions.ResponseFormat));
        AddIf(options.ConversationId is not null, nameof(ChatOptions.ConversationId));
        AddIf(options.AllowBackgroundResponses is true, nameof(ChatOptions.AllowBackgroundResponses));
#pragma warning disable MEAI001 // ContinuationToken is experimental; it is only checked to reject it.
        AddIf(options.ContinuationToken is not null, nameof(ChatOptions.ContinuationToken));
#pragma warning restore MEAI001

        if (unsupported.Count > 0)
        {
            throw new NotSupportedException(
                $"Jev does not support these chat options: {string.Join(", ", unsupported)}. Jev does not generate text; it answers the questions passed with {nameof(JevChatOptionsExtensions.WithJevQuestions)}.");
        }

        if (options.AllowMultipleToolCalls is true)
        {
            throw new NotSupportedException($"Jev requests one tool call per response. Leave {nameof(ChatOptions)}.{nameof(ChatOptions.AllowMultipleToolCalls)} unset or false.");
        }

        void AddIf(bool condition, string name)
        {
            if (condition)
            {
                unsupported.Add(name);
            }
        }
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

    private static List<AIFunctionDeclaration> GetFunctionTools(ChatOptions? options)
    {
        if (options?.Tools is not { Count: > 0 } tools)
        {
            return [];
        }

        List<string> unsupported = [.. tools.Where(tool => tool is not AIFunctionDeclaration).Select(tool => tool.Name)];
        if (unsupported.Count > 0)
        {
            throw new NotSupportedException($"Jev can only call function tools; these tools are not supported: {string.Join(", ", unsupported)}.");
        }

        return [.. tools.Cast<AIFunctionDeclaration>()];
    }

    private static JevResult WithoutInternalAnswers(JevResult result, IReadOnlyDictionary<string, JevQuestion> questions)
    {
        var answers = new Dictionary<string, JevResponse>(questions.Count, StringComparer.Ordinal);
        foreach (string id in questions.Keys)
        {
            answers[id] = result.Answers[id];
        }

        return new JevResult { Model = result.Model, Answers = answers, Usage = result.Usage };
    }

    /// <summary>
    /// Builds the response text: the result as JSON, or, after tool calls, the tool results followed by the Choice and
    /// Score decisions, which is what a caller that reads only text needs to see.
    /// </summary>
    private static string BuildText(IReadOnlyList<ChatMessage> history, int turnStart, JevResult answers)
    {
        List<string> lines = JevChatState.GetCurrentTurnResultTexts(history, turnStart);
        if (lines.Count == 0)
        {
            return JsonSerializer.Serialize(answers, JevJsonContext.Default.JevResult);
        }

        // Noul answers are probabilities rather than decisions, so, as in the Python connector, they are left to the
        // typed result.
        foreach (KeyValuePair<string, JevResponse> answer in answers.Answers)
        {
            switch (answer.Value)
            {
                case JevChoiceResponse choice:
                    lines.Add($"{answer.Key}: {choice.Choice}");
                    break;

                case JevScoreResponse score:
                    lines.Add($"{answer.Key}: {score.Score.ToString("G6", CultureInfo.InvariantCulture)}");
                    break;
            }
        }

        return string.Join("\n", lines);
    }
}
