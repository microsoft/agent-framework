// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="DelegatingAIAgent"/> middleware that implements "don't ask again" tool approval behavior
/// and queues multiple approval requests to present them to the caller one at a time.
/// </summary>
/// <remarks>
/// <para>
/// This middleware intercepts the approval flow between the caller and the inner agent:
/// </para>
/// <list type="bullet">
/// <item>
/// <b>Outbound (response to caller):</b> When the inner agent surfaces <see cref="ToolApprovalRequestContent"/> items,
/// the middleware checks whether matching <see cref="ToolApprovalRule"/> entries have been recorded. Matched requests
/// are auto-approved and stored as collected approval responses. If multiple unapproved requests remain, only the
/// first is returned to the caller while the rest are queued. On subsequent calls, queued items are re-evaluated
/// against rules (which may have been updated by the caller's "always approve" response) and presented one at a time.
/// Once all queued requests are resolved, the collected responses are injected and the inner agent is called again.
/// </item>
/// <item>
/// <b>Inbound (caller to agent):</b> When the caller sends an <see cref="AlwaysApproveToolApprovalResponseContent"/>,
/// the middleware extracts the standing approval settings, records them as <see cref="ToolApprovalRule"/> entries
/// in the session state, and forwards only the unwrapped <see cref="ToolApprovalResponseContent"/> to the inner agent.
/// Content ordering within each message is preserved.
/// </item>
/// </list>
/// <para>
/// Approval rules are persisted in the <see cref="AgentSessionStateBag"/> and survive across agent runs within the same session.
/// Two categories of rules are supported:
/// </para>
/// <list type="bullet">
/// <item><b>Tool-level:</b> Approve all calls to a specific tool, regardless of arguments.</item>
/// <item><b>Tool+arguments:</b> Approve all calls to a specific tool with exactly matching arguments.</item>
/// </list>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ToolApprovalAgent : DelegatingAIAgent
{
    private readonly ProviderSessionState<ToolApprovalState> _sessionState;
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolApprovalAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to delegate to.</param>
    /// <param name="jsonSerializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used for serializing argument values when storing rules
    /// and for persisting state. When <see langword="null"/>, <see cref="AgentJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public ToolApprovalAgent(AIAgent innerAgent, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(innerAgent)
    {
        this._jsonSerializerOptions = jsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
        this._sessionState = new ProviderSessionState<ToolApprovalState>(
            _ => new ToolApprovalState(),
            "toolApprovalState",
            this._jsonSerializerOptions);
    }

    /// <inheritdoc />
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Steps 1–2: Unwrap AlwaysApprove wrappers, process any queued approval requests.
        var (state, callerMessages, nextQueuedItem) = this.PrepareInboundMessages(messages, session);

        if (nextQueuedItem is not null)
        {
            // Queue still has items — return the next one to the caller for approval.
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, [nextQueuedItem]));
        }

        // 3. Call the inner agent in a loop. If the inner agent returns approval requests
        //    that are ALL auto-approved by standing rules, we immediately re-call with the
        //    collected approval responses injected. This avoids returning empty responses.
        while (true)
        {
            // Inject any collected approval responses as a user message ahead of the caller's messages.
            var processedMessages = this.InjectCollectedResponses(callerMessages, state, session);

            var response = await this.InnerAgent.RunAsync(processedMessages, session, options, cancellationToken).ConfigureAwait(false);

            // Classify approval requests: auto-approve matching, queue excess, keep first unapproved.
            bool allAutoApproved = this.ProcessAndQueueOutboundApprovalRequests(response.Messages, state, session);

            if (!allAutoApproved)
            {
                // Response has real content or an unapproved approval request — return to caller.
                return response;
            }

            // All approval requests were auto-approved. Loop to re-invoke with them injected.
            callerMessages = [];
        }
    }

    /// <inheritdoc />
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Steps 1–2: Unwrap AlwaysApprove wrappers, process any queued approval requests.
        var (state, callerMessages, nextQueuedItem) = this.PrepareInboundMessages(messages, session);

        if (nextQueuedItem is not null)
        {
            // Queue still has items — yield the next one to the caller for approval.
            yield return new AgentResponseUpdate(ChatRole.Assistant, [nextQueuedItem]);
            yield break;
        }

        // 3. Stream from the inner agent in a loop. If all approval requests from the stream
        //    are auto-approved by standing rules, we immediately re-stream with the collected
        //    approval responses injected. This avoids returning empty streams.
        while (true)
        {
            // Inject any collected approval responses as a user message ahead of the caller's messages.
            var processedMessages = this.InjectCollectedResponses(callerMessages, state, session);

            // Stream from the inner agent. Non-approval content is yielded immediately.
            // Approval requests are collected (not yielded) so we can classify the full batch.
            List<ToolApprovalRequestContent> streamedApprovalRequests = [];

            await foreach (var update in this.InnerAgent.RunStreamingAsync(processedMessages, session, options, cancellationToken).ConfigureAwait(false))
            {
                // Fast path: no approval content in this update — yield as-is.
                bool hasApprovalRequests = false;
                foreach (var content in update.Contents)
                {
                    if (content is ToolApprovalRequestContent)
                    {
                        hasApprovalRequests = true;
                        break;
                    }
                }

                if (!hasApprovalRequests)
                {
                    yield return update;
                    continue;
                }

                // Split the update: collect approval requests, keep other content.
                var filteredContents = new List<AIContent>();
                foreach (var content in update.Contents)
                {
                    if (content is ToolApprovalRequestContent tarc)
                    {
                        streamedApprovalRequests.Add(tarc);
                    }
                    else
                    {
                        filteredContents.Add(content);
                    }
                }

                // Yield the non-approval portion of the update (if any) as a cloned update.
                if (filteredContents.Count > 0)
                {
                    yield return new AgentResponseUpdate(update.Role, filteredContents)
                    {
                        AuthorName = update.AuthorName,
                        AdditionalProperties = update.AdditionalProperties,
                        AgentId = update.AgentId,
                        ResponseId = update.ResponseId,
                        MessageId = update.MessageId,
                        CreatedAt = update.CreatedAt,
                        ContinuationToken = update.ContinuationToken,
                        FinishReason = update.FinishReason,
                        RawRepresentation = update.RawRepresentation,
                    };
                }
            }

            // If the stream contained no approval requests, we're done.
            if (streamedApprovalRequests.Count == 0)
            {
                yield break;
            }

            // 4. Classify the collected approval requests against standing rules.
            List<ToolApprovalRequestContent> unapproved = [];
            foreach (var tarc in streamedApprovalRequests)
            {
                if (MatchesRule(tarc, state.Rules, this._jsonSerializerOptions))
                {
                    state.CollectedApprovalResponses.Add(
                        tarc.CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
                }
                else
                {
                    unapproved.Add(tarc);
                }
            }

            // If all were auto-approved, loop to re-invoke the inner agent with them injected.
            if (unapproved.Count == 0)
            {
                callerMessages = [];
                continue;
            }

            // 5. Queue excess unapproved requests and yield only the first to the caller.
            if (unapproved.Count > 1)
            {
                state.QueuedApprovalRequests.AddRange(unapproved.GetRange(1, unapproved.Count - 1));
            }

            this._sessionState.SaveState(session, state);
            yield return new AgentResponseUpdate(ChatRole.Assistant, [unapproved[0]]);
            yield break;
        }
    }

    /// <summary>
    /// Extracts <see cref="ToolApprovalResponseContent"/> instances from the caller's messages
    /// and collects them into <see cref="ToolApprovalState.CollectedApprovalResponses"/>.
    /// Extracted responses are removed from the messages in-place.
    /// </summary>
    private static void CollectApprovalResponsesFromMessages(
        List<ChatMessage> messages,
        ToolApprovalState state)
    {
        // Walk messages in reverse so we can safely remove by index.
        for (int i = messages.Count - 1; i >= 0; i--)
        {
            var message = messages[i];

            // Quick check: does this message contain any approval responses?
            bool hasApprovalResponse = false;
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalResponseContent)
                {
                    hasApprovalResponse = true;
                    break;
                }
            }

            if (!hasApprovalResponse)
            {
                continue;
            }

            // Separate approval responses (→ state) from other content (→ keep in message).
            var remaining = new List<AIContent>(message.Contents.Count);
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalResponseContent response)
                {
                    state.CollectedApprovalResponses.Add(response);
                }
                else
                {
                    remaining.Add(content);
                }
            }

            // Remove the message entirely if it only contained approval responses,
            // otherwise replace it with a clone that has the approval responses stripped.
            if (remaining.Count == 0)
            {
                messages.RemoveAt(i);
            }
            else
            {
                var cloned = message.Clone();
                cloned.Contents = remaining;
                messages[i] = cloned;
            }
        }
    }

    /// <summary>
    /// Re-evaluates queued approval requests against current rules and auto-approves any that now match.
    /// </summary>
    private void DrainAutoApprovableFromQueue(ToolApprovalState state)
    {
        for (int i = state.QueuedApprovalRequests.Count - 1; i >= 0; i--)
        {
            if (MatchesRule(state.QueuedApprovalRequests[i], state.Rules, this._jsonSerializerOptions))
            {
                state.CollectedApprovalResponses.Add(
                    state.QueuedApprovalRequests[i].CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
                state.QueuedApprovalRequests.RemoveAt(i);
            }
        }
    }

    /// <summary>
    /// Performs the common inbound processing shared by both the streaming and non-streaming paths:
    /// <list type="number">
    /// <item>Unwraps <see cref="AlwaysApproveToolApprovalResponseContent"/> wrappers, extracting standing rules.</item>
    /// <item>If there are queued approval requests from a previous batch, collects the caller's responses,
    /// drains any items now resolvable by new rules, and dequeues the next item if any remain.</item>
    /// </list>
    /// </summary>
    /// <returns>
    /// A tuple of (state, processed caller messages, next queued item or <see langword="null"/> if the queue is resolved).
    /// When the returned item is non-null, the caller should return/yield it without calling the inner agent.
    /// </returns>
    private (ToolApprovalState State, List<ChatMessage> CallerMessages, ToolApprovalRequestContent? NextQueuedItem)
        PrepareInboundMessages(IEnumerable<ChatMessage> messages, AgentSession? session)
    {
        var state = this._sessionState.GetOrInitializeState(session);

        // 1. Unwrap any AlwaysApprove wrappers in the caller's messages.
        //    This extracts standing approval rules into state and replaces wrappers with plain responses.
        var callerMessages = UnwrapAlwaysApproveResponses(messages, state, this._jsonSerializerOptions);

        // 2. If there are queued approval requests from a previous batch, handle them
        //    before calling the inner agent.
        if (state.QueuedApprovalRequests.Count > 0)
        {
            // Collect the caller's approval/denial responses for the previously dequeued item
            // and store them in state for the next downstream call.
            CollectApprovalResponsesFromMessages(callerMessages, state);

            // Re-evaluate remaining queued items — the caller may have added new rules
            // (e.g., "always approve this tool") that resolve additional items.
            this.DrainAutoApprovableFromQueue(state);

            if (state.QueuedApprovalRequests.Count > 0)
            {
                // More items remain — dequeue the next one for the caller.
                var next = state.QueuedApprovalRequests[0];
                state.QueuedApprovalRequests.RemoveAt(0);
                this._sessionState.SaveState(session, state);
                return (state, callerMessages, next);
            }

            // Queue fully resolved — caller should proceed to call the inner agent.
        }

        return (state, callerMessages, null);
    }

    /// <summary>
    /// Injects any collected approval responses as user messages before the caller's messages,
    /// then clears the collected responses.
    /// </summary>
    private List<ChatMessage> InjectCollectedResponses(
        List<ChatMessage> callerMessages,
        ToolApprovalState state,
        AgentSession? session)
    {
        if (state.CollectedApprovalResponses.Count > 0)
        {
            List<ChatMessage> result = [new ChatMessage(ChatRole.User, [.. state.CollectedApprovalResponses])];
            result.AddRange(callerMessages);

            state.CollectedApprovalResponses.Clear();
            this._sessionState.SaveState(session, state);

            return result;
        }

        return callerMessages;
    }

    /// <summary>
    /// Processes outbound approval requests from non-streaming response messages.
    /// Auto-approvable requests are collected as responses, and if multiple unapproved requests
    /// remain, only the first is kept in the response while the rest are queued for subsequent calls.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if all TARc items were auto-approved (caller should re-invoke the inner agent);
    /// <see langword="false"/> otherwise.
    /// </returns>
    private bool ProcessAndQueueOutboundApprovalRequests(
        IList<ChatMessage> responseMessages,
        ToolApprovalState state,
        AgentSession? session)
    {
        // Pass 1: Scan all response messages and classify each approval request as
        //         auto-approved (matches a standing rule) or unapproved (needs caller decision).
        var autoApproved = new List<ToolApprovalRequestContent>();
        var unapproved = new List<ToolApprovalRequestContent>();

        foreach (var message in responseMessages)
        {
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent tarc)
                {
                    if (MatchesRule(tarc, state.Rules, this._jsonSerializerOptions))
                    {
                        autoApproved.Add(tarc);
                    }
                    else
                    {
                        unapproved.Add(tarc);
                    }
                }
            }
        }

        // Nothing to process: no auto-approved items and at most one unapproved (no queueing needed).
        if (autoApproved.Count == 0 && unapproved.Count <= 1)
        {
            return false;
        }

        // Store auto-approved responses for later injection into the inner agent.
        foreach (var tarc in autoApproved)
        {
            state.CollectedApprovalResponses.Add(
                tarc.CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
        }

        // If every approval request was auto-approved, strip them all and signal the caller
        // to re-invoke the inner agent immediately with the collected responses.
        if (unapproved.Count == 0)
        {
            RemoveAllToolApprovalRequests(responseMessages);
            this._sessionState.SaveState(session, state);
            return true;
        }

        // Pass 2: Keep only the first unapproved request in the response (for the caller to decide).
        //         Queue the remaining unapproved requests for subsequent one-at-a-time delivery.
        //         Remove all auto-approved and queued items from the response messages.
        var toRemove = new HashSet<ToolApprovalRequestContent>(autoApproved);
        if (unapproved.Count > 1)
        {
            for (int i = 1; i < unapproved.Count; i++)
            {
                toRemove.Add(unapproved[i]);
                state.QueuedApprovalRequests.Add(unapproved[i]);
            }
        }

        // Walk messages in reverse and strip marked items.
        for (int i = responseMessages.Count - 1; i >= 0; i--)
        {
            var message = responseMessages[i];

            // Quick check: does this message contain any items to remove?
            bool hasRemovable = false;
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent tarc && toRemove.Contains(tarc))
                {
                    hasRemovable = true;
                    break;
                }
            }

            if (!hasRemovable)
            {
                continue;
            }

            // Filter out the marked items, keeping everything else.
            var remaining = new List<AIContent>(message.Contents.Count);
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent tarc && toRemove.Contains(tarc))
                {
                    continue;
                }

                remaining.Add(content);
            }

            // Remove the message entirely if it's now empty, otherwise replace with filtered clone.
            if (remaining.Count == 0)
            {
                responseMessages.RemoveAt(i);
            }
            else
            {
                var clonedMessage = message.Clone();
                clonedMessage.Contents = remaining;
                responseMessages[i] = clonedMessage;
            }
        }

        this._sessionState.SaveState(session, state);
        return false;
    }

    /// <summary>
    /// Removes all <see cref="ToolApprovalRequestContent"/> items from response messages.
    /// </summary>
    private static void RemoveAllToolApprovalRequests(IList<ChatMessage> responseMessages)
    {
        // Walk messages in reverse so we can safely remove by index.
        for (int i = responseMessages.Count - 1; i >= 0; i--)
        {
            var message = responseMessages[i];

            // Quick check: does this message contain any approval requests?
            bool hasTarc = false;
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent)
                {
                    hasTarc = true;
                    break;
                }
            }

            if (!hasTarc)
            {
                continue;
            }

            // Keep only non-approval content.
            var remaining = new List<AIContent>(message.Contents.Count);
            foreach (var content in message.Contents)
            {
                if (content is not ToolApprovalRequestContent)
                {
                    remaining.Add(content);
                }
            }

            // Remove the message entirely if it's now empty, otherwise replace with filtered clone.
            if (remaining.Count == 0)
            {
                responseMessages.RemoveAt(i);
            }
            else
            {
                var clonedMessage = message.Clone();
                clonedMessage.Contents = remaining;
                responseMessages[i] = clonedMessage;
            }
        }
    }

    /// <summary>
    /// Scans input messages for <see cref="AlwaysApproveToolApprovalResponseContent"/> instances,
    /// extracts standing approval rules, and replaces them in-place with the unwrapped inner
    /// <see cref="ToolApprovalResponseContent"/>, preserving content ordering.
    /// </summary>
    private static List<ChatMessage> UnwrapAlwaysApproveResponses(
        IEnumerable<ChatMessage> messages,
        ToolApprovalState state,
        JsonSerializerOptions jsonSerializerOptions)
    {
        var messageList = messages as IList<ChatMessage> ?? new List<ChatMessage>(messages);
        var result = new List<ChatMessage>(messageList.Count);
        bool anyModified = false;

        foreach (var message in messageList)
        {
            // Quick check: does this message contain any AlwaysApprove wrappers?
            bool hasAlwaysApprove = false;
            foreach (var content in message.Contents)
            {
                if (content is AlwaysApproveToolApprovalResponseContent)
                {
                    hasAlwaysApprove = true;
                    break;
                }
            }

            if (!hasAlwaysApprove)
            {
                result.Add(message);
                continue;
            }

            // Walk content items, replacing each AlwaysApprove wrapper with its inner response
            // while extracting the standing approval rule into state.
            var newContents = new List<AIContent>(message.Contents.Count);
            foreach (var content in message.Contents)
            {
                if (content is AlwaysApproveToolApprovalResponseContent alwaysApprove)
                {
                    // Extract and store the standing approval rule.
                    if (alwaysApprove.InnerResponse.ToolCall is FunctionCallContent toolCall)
                    {
                        if (alwaysApprove.AlwaysApproveTool)
                        {
                            AddRuleIfNotExists(state, new ToolApprovalRule { ToolName = toolCall.Name });
                        }
                        else if (alwaysApprove.AlwaysApproveToolWithArguments)
                        {
                            AddRuleIfNotExists(state, new ToolApprovalRule
                            {
                                ToolName = toolCall.Name,
                                Arguments = SerializeArguments(toolCall.Arguments, jsonSerializerOptions),
                            });
                        }
                    }

                    // Replace the wrapper with the unwrapped inner response, preserving position.
                    newContents.Add(alwaysApprove.InnerResponse);
                }
                else
                {
                    newContents.Add(content);
                }
            }

            // Clone the original message so all metadata is preserved, then replace contents.
            var clonedMessage = message.Clone();
            clonedMessage.Contents = newContents;
            result.Add(clonedMessage);
            anyModified = true;
        }

        // Avoid allocating a new list if nothing was modified.
        return anyModified ? result : (messageList as List<ChatMessage> ?? messageList.ToList());
    }

    /// <summary>
    /// Determines whether a tool approval request matches any of the stored rules.
    /// </summary>
    internal static bool MatchesRule(
        ToolApprovalRequestContent request,
        IReadOnlyList<ToolApprovalRule> rules,
        JsonSerializerOptions jsonSerializerOptions)
    {
        if (request.ToolCall is not FunctionCallContent functionCall)
        {
            return false;
        }

        foreach (var rule in rules)
        {
            if (!string.Equals(rule.ToolName, functionCall.Name, StringComparison.Ordinal))
            {
                continue;
            }

            // Tool-level rule: matches any arguments
            if (rule.Arguments is null)
            {
                return true;
            }

            // Tool+arguments rule: exact match on all argument values
            if (ArgumentsMatch(rule.Arguments, functionCall.Arguments, jsonSerializerOptions))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Compares stored rule arguments against actual function call arguments for an exact match.
    /// </summary>
    private static bool ArgumentsMatch(IDictionary<string, string> ruleArguments, IDictionary<string, object?>? callArguments, JsonSerializerOptions jsonSerializerOptions)
    {
        if (callArguments is null)
        {
            return ruleArguments.Count == 0;
        }

        if (ruleArguments.Count != callArguments.Count)
        {
            return false;
        }

        foreach (var kvp in ruleArguments)
        {
            if (!callArguments.TryGetValue(kvp.Key, out var callValue))
            {
                return false;
            }

            var serializedCallValue = SerializeArgumentValue(callValue, jsonSerializerOptions);
            if (!string.Equals(kvp.Value, serializedCallValue, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Serializes function call arguments to a string dictionary for storage and comparison.
    /// </summary>
    private static Dictionary<string, string>? SerializeArguments(IDictionary<string, object?>? arguments, JsonSerializerOptions jsonSerializerOptions)
    {
        if (arguments is null || arguments.Count == 0)
        {
            return null;
        }

        var serialized = new Dictionary<string, string>(arguments.Count, StringComparer.Ordinal);
        foreach (var kvp in arguments)
        {
            serialized[kvp.Key] = SerializeArgumentValue(kvp.Value, jsonSerializerOptions);
        }

        return serialized;
    }

    /// <summary>
    /// Serializes a single argument value to its JSON string representation.
    /// </summary>
    private static string SerializeArgumentValue(object? value, JsonSerializerOptions jsonSerializerOptions)
    {
        if (value is null)
        {
            return "null";
        }

        if (value is JsonElement jsonElement)
        {
            return jsonElement.GetRawText();
        }

        return JsonSerializer.Serialize(value, jsonSerializerOptions.GetTypeInfo(value.GetType()));
    }

    /// <summary>
    /// Adds a rule to the state if an equivalent rule does not already exist.
    /// </summary>
    private static void AddRuleIfNotExists(ToolApprovalState state, ToolApprovalRule newRule)
    {
        foreach (var existingRule in state.Rules)
        {
            if (!string.Equals(existingRule.ToolName, newRule.ToolName, StringComparison.Ordinal))
            {
                continue;
            }

            if (existingRule.Arguments is null && newRule.Arguments is null)
            {
                return; // Duplicate tool-level rule
            }

            if (existingRule.Arguments is not null && newRule.Arguments is not null &&
                ArgumentDictionariesEqual(existingRule.Arguments, newRule.Arguments))
            {
                return; // Duplicate tool+args rule
            }
        }

        state.Rules.Add(newRule);
    }

    /// <summary>
    /// Compares two string dictionaries for equality.
    /// </summary>
    private static bool ArgumentDictionariesEqual(IDictionary<string, string> a, IDictionary<string, string> b)
    {
        if (a.Count != b.Count)
        {
            return false;
        }

        foreach (var kvp in a)
        {
            if (!b.TryGetValue(kvp.Key, out var bValue) || !string.Equals(kvp.Value, bValue, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }
}
