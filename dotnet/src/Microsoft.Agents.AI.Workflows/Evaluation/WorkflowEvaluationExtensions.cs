// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Extension methods for evaluating workflow runs.
/// </summary>
public static class WorkflowEvaluationExtensions
{
    /// <summary>
    /// Evaluates a completed workflow run.
    /// </summary>
    /// <param name="run">The completed workflow run.</param>
    /// <param name="evaluator">The evaluator to score results.</param>
    /// <param name="includeOverall">Whether to include an overall evaluation.</param>
    /// <param name="includePerAgent">Whether to include per-agent breakdowns.</param>
    /// <param name="evalName">Display name for this evaluation run.</param>
    /// <param name="splitter">
    /// Optional conversation splitter to apply to all items.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results with optional per-agent sub-results.</returns>
    public static async Task<AgentEvaluationResults> EvaluateAsync(
        this Run run,
        IAgentEvaluator evaluator,
        bool includeOverall = true,
        bool includePerAgent = true,
        string evalName = "Workflow Eval",
        IConversationSplitter? splitter = null,
        CancellationToken cancellationToken = default)
    {
        var events = run.OutgoingEvents.ToList();

        // Extract per-agent data
        var agentData = ExtractAgentData(events, splitter);

        // Build overall items from final output
        var overallItems = new List<EvalItem>();
        if (includeOverall)
        {
            var finalResponse = events.OfType<AgentResponseEvent>().LastOrDefault();
            if (finalResponse is not null)
            {
                var firstInvoked = events.OfType<ExecutorInvokedEvent>().FirstOrDefault();
                var query = firstInvoked?.Data switch
                {
                    ChatMessage cm => cm.Text ?? string.Empty,
                    IReadOnlyList<ChatMessage> msgs => msgs.LastOrDefault(m => m.Role == ChatRole.User)?.Text ?? string.Empty,
                    string s => s,
                    _ => firstInvoked?.Data?.ToString() ?? string.Empty,
                };
                var conversation = new List<ChatMessage>
                {
                    new(ChatRole.User, query),
                };

                conversation.AddRange(finalResponse.Response.Messages);

                overallItems.Add(new EvalItem(query, finalResponse.Response.Text, conversation)
                {
                    Splitter = splitter,
                });
            }
        }

        // Evaluate overall
        var overallResult = overallItems.Count > 0
            ? await evaluator.EvaluateAsync(overallItems, evalName, cancellationToken).ConfigureAwait(false)
            : new AgentEvaluationResults(evaluator.Name, Array.Empty<EvaluationResult>());

        // Per-agent breakdown
        if (includePerAgent && agentData.Count > 0)
        {
            var subResults = new Dictionary<string, AgentEvaluationResults>();

            foreach (var kvp in agentData)
            {
                subResults[kvp.Key] = await evaluator.EvaluateAsync(
                    kvp.Value,
                    $"{evalName} - {kvp.Key}",
                    cancellationToken).ConfigureAwait(false);
            }

            overallResult.SubResults = subResults;
        }

        return overallResult;
    }

    internal static Dictionary<string, List<EvalItem>> ExtractAgentData(
        List<WorkflowEvent> events,
        IConversationSplitter? splitter)
    {
        var invoked = new Dictionary<string, ExecutorInvokedEvent>();
        var agentData = new Dictionary<string, List<EvalItem>>();

        foreach (var evt in events)
        {
            if (evt is ExecutorInvokedEvent invokedEvent)
            {
                if (IsInternalExecutor(invokedEvent.ExecutorId))
                {
                    continue;
                }

                invoked[invokedEvent.ExecutorId] = invokedEvent;
            }
            else if (evt is ExecutorCompletedEvent completedEvent
                     && invoked.TryGetValue(completedEvent.ExecutorId, out var matchingInvoked))
            {
                var query = matchingInvoked.Data switch
                {
                    ChatMessage cm => cm.Text ?? string.Empty,
                    IReadOnlyList<ChatMessage> msgs => msgs.LastOrDefault(m => m.Role == ChatRole.User)?.Text ?? string.Empty,
                    string s => s,
                    _ => matchingInvoked.Data?.ToString() ?? string.Empty,
                };

                var responseText = completedEvent.Data switch
                {
                    AgentResponse ar => ar.Text,
                    ChatMessage cm => cm.Text ?? string.Empty,
                    string s => s,
                    _ => completedEvent.Data?.ToString() ?? string.Empty,
                };
                var agentResponse = completedEvent.Data as AgentResponse;
                var conversation = new List<ChatMessage>
                {
                    new(ChatRole.User, query),
                };

                if (agentResponse is not null)
                {
                    conversation.AddRange(agentResponse.Messages);
                }
                else
                {
                    conversation.Add(new(ChatRole.Assistant, responseText));
                }

                var item = new EvalItem(query, responseText, conversation)
                {
                    Splitter = splitter,
                };

                if (!agentData.TryGetValue(completedEvent.ExecutorId, out var items))
                {
                    items = new List<EvalItem>();
                    agentData[completedEvent.ExecutorId] = items;
                }

                items.Add(item);
                invoked.Remove(completedEvent.ExecutorId);
            }
        }

        return agentData;
    }

    private static bool IsInternalExecutor(string executorId)
    {
        return executorId.StartsWith('_')
            || executorId is "input-conversation" or "end-conversation" or "end";
    }
}
