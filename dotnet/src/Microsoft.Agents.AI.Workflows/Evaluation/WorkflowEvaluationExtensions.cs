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
    /// <param name="expectedOutput">
    /// Optional ground-truth/expected output for the workflow's overall final answer.
    /// When provided, it is stamped onto the overall <see cref="EvalItem.ExpectedOutput"/>
    /// so reference-based evaluators (for example, similarity) can compare the
    /// workflow's response against a golden answer. Ground truth is only applied
    /// to the overall item; per-agent items are intentionally left without an
    /// expected output, since ground truth is defined against the final response.
    /// When using a reference-based evaluator that requires ground truth, set
    /// <paramref name="includePerAgent"/> to <see langword="false"/> to avoid
    /// invoking the evaluator on per-agent items that have no expected output.
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
        string? expectedOutput = null,
        CancellationToken cancellationToken = default)
    {
        var events = run.OutgoingEvents.ToList();

        // Extract per-agent data
        var agentData = ExtractAgentData(events, splitter);

        // Build overall items from final output
        var overallItems = new List<EvalItem>();
        if (includeOverall)
        {
            var overallItem = BuildOverallItem(events, splitter, expectedOutput);
            if (overallItem is not null)
            {
                overallItems.Add(overallItem);
            }
            else
            {
                // The caller asked for an overall evaluation but we couldn't find a final
                // response to score — almost always because the workflow's agents weren't
                // built with EmitAgentResponseEvents enabled (so no AgentResponseEvent was
                // emitted) and no terminal ExecutorCompletedEvent carried an AgentResponse
                // / ChatMessage / string payload. Fail loudly instead of silently returning
                // 0/0 (or skipping evaluation against a supplied expectedOutput).
                throw new InvalidOperationException(
                    "Cannot evaluate the overall workflow output: no AgentResponseEvent or " +
                    "ExecutorCompletedEvent with an AgentResponse/ChatMessage/string payload " +
                    "was found in the run. Bind agents with " +
                    "AIAgentHostOptions { EmitAgentResponseEvents = true } " +
                    "(for example via agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true })) " +
                    "so the workflow surfaces the final agent response, or set 'includeOverall: false'.");
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

    internal static EvalItem? BuildOverallItem(
        IReadOnlyList<WorkflowEvent> events,
        IConversationSplitter? splitter,
        string? expectedOutput)
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

        // Prefer AgentResponseEvent (only emitted when AIAgentHostOptions.EmitAgentResponseEvents
        // is enabled). Otherwise fall back to the last ExecutorCompletedEvent that carries an
        // AgentResponse / ChatMessage / string payload — these are always emitted by the runtime.
        var finalResponse = events.OfType<AgentResponseEvent>().LastOrDefault();
        string responseText;
        if (finalResponse is not null)
        {
            responseText = finalResponse.Response.Text;
            conversation.AddRange(finalResponse.Response.Messages);
        }
        else
        {
            ExecutorCompletedEvent? finalCompleted = null;
            for (int i = events.Count - 1; i >= 0; i--)
            {
                if (events[i] is ExecutorCompletedEvent completed
                    && !IsInternalExecutor(completed.ExecutorId)
                    && completed.Data is AgentResponse or ChatMessage or string)
                {
                    finalCompleted = completed;
                    break;
                }
            }

            if (finalCompleted is null)
            {
                return null;
            }

            switch (finalCompleted.Data)
            {
                case AgentResponse ar:
                    responseText = ar.Text;
                    conversation.AddRange(ar.Messages);
                    break;
                case ChatMessage cm:
                    responseText = cm.Text ?? string.Empty;
                    conversation.Add(cm);
                    break;
                case string s:
                    responseText = s;
                    conversation.Add(new ChatMessage(ChatRole.Assistant, s));
                    break;
                default:
                    // Unreachable — the for-loop above already constrains Data to one of the
                    // three handled types. Throw if the contract drifts so the bug is visible
                    // instead of silently dropping the overall item.
                    throw new InvalidOperationException(
                        "BuildOverallItem: unexpected ExecutorCompletedEvent.Data type " +
                        $"'{finalCompleted.Data?.GetType().FullName ?? "null"}'. Expected " +
                        $"{nameof(AgentResponse)}, {nameof(ChatMessage)}, or string.");
            }
        }

        return new EvalItem(query, responseText, conversation)
        {
            Splitter = splitter,
            ExpectedOutput = expectedOutput,
        };
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
