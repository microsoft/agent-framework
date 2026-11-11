// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// Answers chat requests with a decision model, which answers typed questions about a state instead of writing text.
/// </summary>
/// <remarks>
/// <para>
/// This is the provider-neutral part of a decision model chat client. Each request sends the conversation as the state
/// (see <see cref="DecisionChatState"/>), together with the caller's questions and the internal questions that let the
/// model call a function tool whose arguments come from a closed set (see <see cref="DecisionToolCallCompiler"/>). The
/// response is a <see cref="FunctionCallContent"/> for a function-invoking client to run, or the answers to the
/// caller's questions. Once the turn has used <see cref="DecisionChatEngineOptions.MaximumToolCallsPerTurn"/> calls,
/// tools are no longer offered, which ends the function-invoking loop.
/// </para>
/// <para>
/// A provider's public chat client supplies the <see cref="IDecisionClient"/>, converts its own question types into
/// <see cref="DecisionQuestion"/> values, and describes the answers in its own result type through
/// <see cref="DecisionChatEngineOptions.DescribeAnswers"/>. The engine uses only the public surface of the decision
/// API, so it compiles unchanged against <c>Microsoft.Extensions.AI</c> once that API ships.
/// </para>
/// </remarks>
internal sealed class DecisionChatEngine
{
    private readonly IDecisionClient _client;
    private readonly DecisionChatEngineOptions _options;

    public DecisionChatEngine(IDecisionClient client, DecisionChatEngineOptions options)
    {
        this._client = Throw.IfNull(client);
        this._options = Throw.IfNull(options);
    }

    /// <summary>
    /// Answers one chat request.
    /// </summary>
    /// <param name="messages">The conversation.</param>
    /// <param name="options">The chat options, which supply the tools, the tool mode, and the instructions.</param>
    /// <param name="questions">The caller's questions, which the answer text and raw representation describe.</param>
    /// <param name="decisionOptions">The options passed to the decision client, such as the model ID.</param>
    /// <param name="cancellationToken">The cancellation token to monitor.</param>
    /// <returns>A tool call, or the answers to <paramref name="questions"/>.</returns>
    /// <exception cref="ArgumentException">A message or question is invalid.</exception>
    /// <exception cref="InvalidOperationException">
    /// A required tool call is impossible, or the decision response does not answer every question as asked.
    /// </exception>
    /// <exception cref="NotSupportedException">The request uses an option, tool, or content that the model does not support.</exception>
    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options,
        IReadOnlyList<DecisionQuestion> questions,
        DecisionOptions? decisionOptions,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(messages);
        _ = Throw.IfNull(questions);
        IReadOnlyList<ChatMessage> history = messages as IReadOnlyList<ChatMessage> ?? [.. messages];
        string modelName = this._options.ModelName;

        this.EnsureSupported(options);
        if (questions.Count == 0)
        {
            Throw.ArgumentException(nameof(questions), $"{modelName} needs at least one question.");
        }

        DecisionToolCallCompiler.EnsureNoReservedQuestionIds(questions.Select(question => question.Id));
        List<AIFunctionDeclaration> tools = this.GetFunctionTools(options);

        // Once the turn has used its tool calls, tools are no longer offered, so the next response answers the
        // questions with the tool results in the state. This is what ends the function-invoking loop, like the
        // max_function_calls default of one in the Python TypeSafe connector.
        int turnStart = DecisionChatState.GetCurrentTurnStart(history);
        ChatToolMode? toolMode = DecisionChatState.CountCurrentTurnCalls(history, turnStart) >= this._options.MaximumToolCallsPerTurn
            ? ChatToolMode.None
            : options?.ToolMode;
        DecisionToolCallPlan? plan = DecisionToolCallCompiler.Compile(
            tools,
            toolMode,
            DecisionChatState.GetCurrentTurnCalls(history, turnStart),
            modelName,
            this._options.Logger);

        // The reserved prefix keeps the internal question IDs apart from the caller's.
        List<DecisionQuestion> allQuestions = [.. questions, .. plan?.Questions.Values ?? []];
        var request = new DecisionRequest(DecisionChatState.Build(history, options?.Instructions, modelName), allQuestions);

        DecisionResponse response;
        try
        {
            response = await this._client.GetResponseAsync(request, decisionOptions, cancellationToken).ConfigureAwait(false);
        }
        catch (DecisionProtocolException ex)
        {
            // A response that does not answer the questions as asked is a provider failure, which callers of a chat
            // client see as an InvalidOperationException.
            throw new InvalidOperationException($"The {modelName} response is invalid: {ex.Message}", ex);
        }

        if (plan?.Decode(response) is { } call)
        {
            var callMessage = new ChatMessage(
                ChatRole.Assistant,
                [new FunctionCallContent($"{this._options.CallIdPrefix}-{Guid.NewGuid():N}", call.Function.Name, call.Arguments)]);
            return new ChatResponse(callMessage)
            {
                ModelId = response.Provenance?.ModelId,
                FinishReason = ChatFinishReason.ToolCalls,
                Usage = response.Usage,
                CreatedAt = DateTimeOffset.UtcNow,
            };
        }

        // The caller asked only its own questions, so the internal tool answers are removed from what it sees.
        DecisionResponse answers = OnlyAnswersTo(response, questions);
        DecisionChatAnswers described = this._options.DescribeAnswers(answers);
        var message = new ChatMessage(ChatRole.Assistant, BuildText(history, turnStart, answers, described.Text))
        {
            RawRepresentation = described.RawRepresentation,
        };

        return new ChatResponse(message)
        {
            ModelId = response.Provenance?.ModelId,
            FinishReason = ChatFinishReason.Stop,
            Usage = response.Usage,
            CreatedAt = DateTimeOffset.UtcNow,
            RawRepresentation = described.RawRepresentation,
        };
    }

    private void EnsureSupported(ChatOptions? options)
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

        string modelName = this._options.ModelName;
        if (unsupported.Count > 0)
        {
            throw new NotSupportedException(
                $"{modelName} does not support these chat options: {string.Join(", ", unsupported)}. {modelName} does not generate text; it answers {this._options.QuestionsDescription}.");
        }

        if (options.AllowMultipleToolCalls is true)
        {
            throw new NotSupportedException($"{modelName} requests one tool call per response. Leave {nameof(ChatOptions)}.{nameof(ChatOptions.AllowMultipleToolCalls)} unset or false.");
        }

        void AddIf(bool condition, string name)
        {
            if (condition)
            {
                unsupported.Add(name);
            }
        }
    }

    private List<AIFunctionDeclaration> GetFunctionTools(ChatOptions? options)
    {
        if (options?.Tools is not { Count: > 0 } tools)
        {
            return [];
        }

        List<string> unsupported = [.. tools.Where(tool => tool is not AIFunctionDeclaration).Select(tool => tool.Name)];
        if (unsupported.Count > 0)
        {
            throw new NotSupportedException($"{this._options.ModelName} can only call function tools; these tools are not supported: {string.Join(", ", unsupported)}.");
        }

        return [.. tools.Cast<AIFunctionDeclaration>()];
    }

    private static DecisionResponse OnlyAnswersTo(DecisionResponse response, IReadOnlyList<DecisionQuestion> questions)
    {
        if (response.Answers.Count == questions.Count)
        {
            return response;
        }

        var answers = new Dictionary<string, DecisionAnswer>(response.Answers.Count, StringComparer.Ordinal);
        foreach (DecisionAnswer answer in response.Answers)
        {
            answers[answer.QuestionId] = answer;
        }

        return new DecisionResponse(
            new DecisionRequest(response.Request.State, questions),
            [.. questions.Select(question => answers[question.Id])],
            response.Provenance,
            response.Usage,
            response.RawRepresentation,
            response.AdditionalProperties);
    }

    /// <summary>
    /// Builds the response text: the described answers, or, after tool calls, the tool results followed by the Choice
    /// and Score decisions, which is what a caller that reads only text needs to see.
    /// </summary>
    private static string BuildText(IReadOnlyList<ChatMessage> history, int turnStart, DecisionResponse answers, string describedAnswers)
    {
        List<string> lines = DecisionChatState.GetCurrentTurnResultTexts(history, turnStart);
        if (lines.Count == 0)
        {
            return describedAnswers;
        }

        // Binary answers are probabilities rather than decisions, so, as in the Python TypeSafe connector, they are left
        // to the typed result.
        foreach (DecisionAnswer answer in answers.Answers)
        {
            switch (answer)
            {
                case ChoiceDecisionAnswer choice:
                    lines.Add($"{answer.QuestionId}: {choice.SelectedCandidateId}");
                    break;

                case ScoreDecisionAnswer score:
                    lines.Add($"{answer.QuestionId}: {(score.Score ?? score.ExpectedScore).ToString("G6", CultureInfo.InvariantCulture)}");
                    break;
            }
        }

        return string.Join("\n", lines);
    }
}
