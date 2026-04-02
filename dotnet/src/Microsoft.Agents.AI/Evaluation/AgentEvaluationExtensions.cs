// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI;

/// <summary>
/// Extension methods for evaluating agents, responses, and workflow runs.
/// </summary>
public static partial class AgentEvaluationExtensions
{
    private const string DefaultEvalName = "AgentFrameworkEval";

    /// <summary>
    /// Evaluates an agent by running it against test queries and scoring the responses.
    /// </summary>
    /// <param name="agent">The agent to evaluate.</param>
    /// <param name="queries">Test queries to send to the agent.</param>
    /// <param name="evaluator">The evaluator to score responses.</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="expectedOutput">
    /// Optional ground-truth expected outputs, one per query. When provided,
    /// must be the same length as <paramref name="queries"/>. Each value is
    /// stamped on the corresponding <see cref="EvalItem.ExpectedOutput"/>.
    /// </param>
    /// <param name="expectedToolCalls">
    /// Optional expected tool calls, one list per query. When provided,
    /// must be the same length as <paramref name="queries"/>. Each list is
    /// stamped on the corresponding <see cref="EvalItem.ExpectedToolCalls"/>.
    /// </param>
    /// <param name="splitter">
    /// Optional conversation splitter to apply to all items.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="numRepetitions">
    /// Number of times to run each query (default 1). When greater than 1, each query is invoked
    /// independently N times to measure consistency. Results contain all N × queries.Count items.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results.</returns>
    public static async Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<string> queries,
        IAgentEvaluator evaluator,
        string evalName = DefaultEvalName,
        IEnumerable<string>? expectedOutput = null,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls = null,
        IConversationSplitter? splitter = null,
        int numRepetitions = 1,
        CancellationToken cancellationToken = default)
    {
        var items = await RunAgentForEvalAsync(agent, queries, expectedOutput, expectedToolCalls, splitter, numRepetitions, cancellationToken).ConfigureAwait(false);
        return await evaluator.EvaluateAsync(items, evalName, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Evaluates an agent using an MEAI evaluator directly.
    /// </summary>
    /// <param name="agent">The agent to evaluate.</param>
    /// <param name="queries">Test queries to send to the agent.</param>
    /// <param name="evaluator">The MEAI evaluator (e.g., <c>RelevanceEvaluator</c>, <c>CompositeEvaluator</c>).</param>
    /// <param name="chatConfiguration">Chat configuration for the MEAI evaluator (includes the judge model).</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="expectedOutput">
    /// Optional ground-truth expected outputs, one per query.
    /// </param>
    /// <param name="expectedToolCalls">
    /// Optional expected tool calls, one list per query.
    /// </param>
    /// <param name="splitter">
    /// Optional conversation splitter to apply to all items.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="numRepetitions">
    /// Number of times to run each query (default 1). When greater than 1, each query is invoked
    /// independently N times to measure consistency.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results.</returns>
    public static async Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<string> queries,
        IEvaluator evaluator,
        ChatConfiguration chatConfiguration,
        string evalName = DefaultEvalName,
        IEnumerable<string>? expectedOutput = null,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls = null,
        IConversationSplitter? splitter = null,
        int numRepetitions = 1,
        CancellationToken cancellationToken = default)
    {
        var wrapped = new MeaiEvaluatorAdapter(evaluator, chatConfiguration);
        return await agent.EvaluateAsync(queries, wrapped, evalName, expectedOutput, expectedToolCalls, splitter, numRepetitions, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Evaluates an agent by running it against test queries with multiple evaluators.
    /// </summary>
    /// <param name="agent">The agent to evaluate.</param>
    /// <param name="queries">Test queries to send to the agent.</param>
    /// <param name="evaluators">The evaluators to score responses.</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="expectedOutput">
    /// Optional ground-truth expected outputs, one per query.
    /// </param>
    /// <param name="expectedToolCalls">
    /// Optional expected tool calls, one list per query.
    /// </param>
    /// <param name="splitter">
    /// Optional conversation splitter to apply to all items.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="numRepetitions">
    /// Number of times to run each query (default 1). When greater than 1, each query is invoked
    /// independently N times to measure consistency.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>One result per evaluator.</returns>
    public static async Task<IReadOnlyList<AgentEvaluationResults>> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<string> queries,
        IEnumerable<IAgentEvaluator> evaluators,
        string evalName = DefaultEvalName,
        IEnumerable<string>? expectedOutput = null,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls = null,
        IConversationSplitter? splitter = null,
        int numRepetitions = 1,
        CancellationToken cancellationToken = default)
    {
        var items = await RunAgentForEvalAsync(agent, queries, expectedOutput, expectedToolCalls, splitter, numRepetitions, cancellationToken).ConfigureAwait(false);

        var results = new List<AgentEvaluationResults>();
        foreach (var evaluator in evaluators)
        {
            var result = await evaluator.EvaluateAsync(items, evalName, cancellationToken).ConfigureAwait(false);
            results.Add(result);
        }

        return results;
    }

    /// <summary>
    /// Evaluates pre-existing agent responses without re-running the agent.
    /// </summary>
    /// <param name="agent">The agent (used for tool definitions).</param>
    /// <param name="responses">Pre-existing agent responses.</param>
    /// <param name="queries">The queries that produced each response (must match count).</param>
    /// <param name="evaluator">The evaluator to score responses.</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="expectedOutput">
    /// Optional ground-truth expected outputs, one per query.
    /// </param>
    /// <param name="expectedToolCalls">
    /// Optional expected tool calls, one list per query.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results.</returns>
    public static async Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<AgentResponse> responses,
        IEnumerable<string> queries,
        IAgentEvaluator evaluator,
        string evalName = DefaultEvalName,
        IEnumerable<string>? expectedOutput = null,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls = null,
        CancellationToken cancellationToken = default)
    {
        var items = BuildItemsFromResponses(agent, responses, queries, expectedOutput, expectedToolCalls);
        return await evaluator.EvaluateAsync(items, evalName, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Evaluates pre-existing agent responses using an MEAI evaluator directly.
    /// </summary>
    /// <param name="agent">The agent (used for tool definitions).</param>
    /// <param name="responses">Pre-existing agent responses.</param>
    /// <param name="queries">The queries that produced each response (must match count).</param>
    /// <param name="evaluator">The MEAI evaluator.</param>
    /// <param name="chatConfiguration">Chat configuration for the MEAI evaluator.</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="expectedOutput">
    /// Optional ground-truth expected outputs, one per query.
    /// </param>
    /// <param name="expectedToolCalls">
    /// Optional expected tool calls, one list per query.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results.</returns>
    public static async Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<AgentResponse> responses,
        IEnumerable<string> queries,
        IEvaluator evaluator,
        ChatConfiguration chatConfiguration,
        string evalName = DefaultEvalName,
        IEnumerable<string>? expectedOutput = null,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls = null,
        CancellationToken cancellationToken = default)
    {
        var wrapped = new MeaiEvaluatorAdapter(evaluator, chatConfiguration);
        return await agent.EvaluateAsync(responses, queries, wrapped, evalName, expectedOutput, expectedToolCalls, cancellationToken).ConfigureAwait(false);
    }

    internal static List<EvalItem> BuildItemsFromResponses(
        AIAgent agent,
        IEnumerable<AgentResponse> responses,
        IEnumerable<string> queries,
        IEnumerable<string>? expectedOutput,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls)
    {
        var responseList = responses.ToList();
        var queryList = queries.ToList();
        var expectedList = expectedOutput?.ToList();
        var expectedToolCallsList = expectedToolCalls?.ToList();

        if (responseList.Count != queryList.Count)
        {
            throw new ArgumentException(
                $"Found {queryList.Count} queries but {responseList.Count} responses. Counts must match.");
        }

        if (expectedList != null && expectedList.Count != queryList.Count)
        {
            throw new ArgumentException(
                $"Found {queryList.Count} queries but {expectedList.Count} expectedOutput values. Counts must match.");
        }

        if (expectedToolCallsList != null && expectedToolCallsList.Count != queryList.Count)
        {
            throw new ArgumentException(
                $"Found {queryList.Count} queries but {expectedToolCallsList.Count} expectedToolCalls lists. Counts must match.");
        }

        var items = new List<EvalItem>();
        for (int i = 0; i < responseList.Count; i++)
        {
            var query = queryList[i];
            var response = responseList[i];

            var messages = new List<ChatMessage>
            {
                new(ChatRole.User, query),
            };
            messages.AddRange(response.Messages);

            var item = BuildEvalItem(query, response, messages, agent);
            if (expectedList != null)
            {
                item.ExpectedOutput = expectedList[i];
            }

            if (expectedToolCallsList != null)
            {
                item.ExpectedToolCalls = expectedToolCallsList[i].ToList();
            }

            items.Add(item);
        }

        return items;
    }

    private static async Task<List<EvalItem>> RunAgentForEvalAsync(
        AIAgent agent,
        IEnumerable<string> queries,
        IEnumerable<string>? expectedOutput,
        IEnumerable<IEnumerable<ExpectedToolCall>>? expectedToolCalls,
        IConversationSplitter? splitter,
        int numRepetitions,
        CancellationToken cancellationToken)
    {
        if (numRepetitions < 1)
        {
            throw new ArgumentException($"numRepetitions must be >= 1, got {numRepetitions}.", nameof(numRepetitions));
        }

        var items = new List<EvalItem>();
        var queryList = queries.ToList();
        var expectedList = expectedOutput?.ToList();
        var expectedToolCallsList = expectedToolCalls?.ToList();

        if (expectedList != null && expectedList.Count != queryList.Count)
        {
            throw new ArgumentException(
                $"Got {queryList.Count} queries but {expectedList.Count} expectedOutput values. Counts must match.");
        }

        if (expectedToolCallsList != null && expectedToolCallsList.Count != queryList.Count)
        {
            throw new ArgumentException(
                $"Got {queryList.Count} queries but {expectedToolCallsList.Count} expectedToolCalls lists. Counts must match.");
        }

        for (int rep = 0; rep < numRepetitions; rep++)
        {
            for (int i = 0; i < queryList.Count; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();

                var query = queryList[i];
                var messages = new List<ChatMessage>
                {
                    new(ChatRole.User, query),
                };

                var response = await agent.RunAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false);
                var item = BuildEvalItem(query, response, messages, agent);
                item.Splitter = splitter;
                if (expectedList != null)
                {
                    item.ExpectedOutput = expectedList[i];
                }

                if (expectedToolCallsList != null)
                {
                    item.ExpectedToolCalls = expectedToolCallsList[i].ToList();
                }

                items.Add(item);
            }
        }

        return items;
    }

    internal static EvalItem BuildEvalItem(
        string query,
        AgentResponse response,
        List<ChatMessage> messages,
        AIAgent? agent)
    {
        // Build conversation from existing messages plus any new response messages
        var conversation = new List<ChatMessage>(messages);
        foreach (var msg in response.Messages)
        {
            if (!conversation.Contains(msg))
            {
                conversation.Add(msg);
            }
        }

        var item = new EvalItem(query, response.Text, conversation)
        {
            RawResponse = new ChatResponse(response.Messages.LastOrDefault()
                ?? new ChatMessage(ChatRole.Assistant, response.Text)),
        };

        // Extract tool definitions from the agent (mirrors Python's to_eval_item(agent=...))
        if (agent is not null)
        {
            var chatOptions = agent.GetService<ChatOptions>();
            if (chatOptions?.Tools is { Count: > 0 } tools)
            {
                item.Tools = tools.ToList().AsReadOnly();
            }
        }

        return item;
    }
}
