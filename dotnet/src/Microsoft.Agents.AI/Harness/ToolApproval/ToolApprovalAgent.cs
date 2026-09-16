// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

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
/// This one-at-a-time behavior no longer applies once the auto-approval cap
/// (<see cref="ToolApprovalAgentOptions.MaxAutoApprovalIterations"/>) is reached: the final inner turn is returned
/// as-is, so more than one approval request may be surfaced to the caller at once.
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
public sealed class ToolApprovalAgent : DelegatingAIAgent
{
    /// <summary>The default value used for <see cref="ToolApprovalAgentOptions.MaxAutoApprovalIterations"/> when none is specified.</summary>
    public const int DefaultMaxAutoApprovalIterations = 40;

    private readonly ProviderSessionState<ToolApprovalState> _sessionState;
    private readonly JsonSerializerOptions _jsonSerializerOptions;
    private readonly Func<ToolAutoApprovalRuleContext, ValueTask<bool>>[]? _autoApprovalRules;
    private readonly int _maxAutoApprovalIterations;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolApprovalAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to delegate to.</param>
    /// <param name="options">
    /// Optional <see cref="ToolApprovalAgentOptions"/> for configuring serialization and auto-approval rules.
    /// When <see langword="null"/>, default settings are used.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public ToolApprovalAgent(AIAgent innerAgent, ToolApprovalAgentOptions? options = null)
        : base(innerAgent)
    {
        this._jsonSerializerOptions = options?.JsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
        this._autoApprovalRules = options?.AutoApprovalRules?.ToArray();
        this._maxAutoApprovalIterations = Throw.IfLessThan(
            options?.MaxAutoApprovalIterations ?? DefaultMaxAutoApprovalIterations, 1);
        this._sessionState = new ProviderSessionState<ToolApprovalState>(
            _ => new ToolApprovalState(),
            "toolApprovalState",
            this._jsonSerializerOptions);
    }

    /// <summary>
    /// Gets an auto-approval rule that approves every tool call, regardless of tool name or arguments.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Add this rule to <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve all
    /// tool calls without prompting the user. This effectively disables approval prompts for every tool, so use
    /// it only when running in a fully trusted context.
    /// </para>
    /// <para>
    /// For example, to auto-approve every tool call:
    /// <code>
    /// builder.UseToolApproval(new ToolApprovalAgentOptions
    /// {
    ///     AutoApprovalRules = [ToolApprovalAgent.AllToolsAutoApprovalRule],
    /// });
    /// </code>
    /// </para>
    /// <para>
    /// <b>Security note:</b> this rule is name-agnostic and approves <b>every</b> tool call regardless
    /// of the tool name (<see cref="FunctionCallContent.Name"/>) or arguments. Only use this rule in a fully trusted context.
    /// </para>
    /// </remarks>
    public static Func<ToolAutoApprovalRuleContext, ValueTask<bool>> AllToolsAutoApprovalRule { get; } =
        _ => new ValueTask<bool>(true);

    /// <inheritdoc />
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.CoreToolApproval);
#pragma warning restore MAAI001

        var requestMessages = messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        // Steps 1–2: Unwrap AlwaysApprove wrappers, process any queued approval requests.
        var (state, callerMessages, nextQueuedItem) = await this.PrepareInboundMessagesAsync(requestMessages, session, options).ConfigureAwait(false);

        if (nextQueuedItem is not null)
        {
            // Queue still has items — return the next one to the caller for approval.
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, [nextQueuedItem]));
        }

        // When the caller did not supply a session, create one and use it for every inner call.
        // The auto-approval loop re-invokes the inner agent with only the injected approval
        // responses; without a session the inner agent has no conversation history to reconstruct
        // the original request, which produces an empty request to the underlying service. Threading
        // a session preserves the history across re-invocations.
        session ??= await this.InnerAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        // 3. Call the inner agent in a loop. If the inner agent returns approval requests
        //    that are ALL auto-approved by standing rules, we immediately re-call with the
        //    collected approval responses injected. This avoids returning empty responses.
        //
        //    The loop is bounded by _maxAutoApprovalIterations. Each pass is a fresh inner
        //    invocation, so a per-request cap (FunctionInvokingChatClient.MaximumIterationsPerRequest)
        //    restarts every time and cannot bound it; without a cap here a model that keeps
        //    requesting an auto-approved tool bills indefinitely.
        //
        //    Usage is accumulated across every re-invocation so the caller sees the token cost
        //    of the whole run, not just its final inner call.
        UsageDetails? aggregatedUsage = null;

        for (int iteration = 0; ; iteration++)
        {
            // Inject any collected approval responses as a user message ahead of the caller's messages.
            var processedMessages = this.InjectCollectedResponses(callerMessages, state, session);

            if (iteration >= this._maxAutoApprovalIterations)
            {
                // Cap reached: take one final turn without auto-approving again, so any approval
                // request it surfaces goes to the caller to decide rather than continuing the chain.
                // Returning here without this call would hand back a response whose approval requests
                // were already stripped — the empty response the loop exists to avoid.
                var cappedResponse = await this.InnerAgent.RunAsync(processedMessages, session, options, cancellationToken).ConfigureAwait(false);

                // Any approval requests in this turn go straight to the caller, so record them as surfaced.
                // Without this, a legitimate always-approve response to them could not be bound.
                this.RecordSurfacedApprovalRequestsFromMessages(cappedResponse.Messages, state, session);

                // This turn is still part of the same run, so its usage joins the aggregate rather
                // than replacing it; otherwise hitting the cap would discard every prior turn's cost.
                UsageAggregator.Accumulate(ref aggregatedUsage, cappedResponse.Usage);

                return cappedResponse.ApplyAggregatedUsage(aggregatedUsage);
            }

            var response = await this.InnerAgent.RunAsync(processedMessages, session, options, cancellationToken).ConfigureAwait(false);

            UsageAggregator.Accumulate(ref aggregatedUsage, response.Usage);

            // Classify approval requests: auto-approve matching, queue excess, keep first unapproved.
            bool allAutoApproved = await this.ProcessAndQueueOutboundApprovalRequestsAsync(response.Messages, state, session, options, requestMessages).ConfigureAwait(false);

            if (!allAutoApproved)
            {
                // Response has real content or an unapproved approval request — return to caller,
                // reporting the usage accumulated across every turn of the run.
                return response.ApplyAggregatedUsage(aggregatedUsage);
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
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.CoreToolApproval);
#pragma warning restore MAAI001

        var requestMessages = messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        // Steps 1–2: Unwrap AlwaysApprove wrappers, process any queued approval requests.
        var (state, callerMessages, nextQueuedItem) = await this.PrepareInboundMessagesAsync(requestMessages, session, options).ConfigureAwait(false);

        if (nextQueuedItem is not null)
        {
            // Queue still has items — yield the next one to the caller for approval.
            yield return new AgentResponseUpdate(ChatRole.Assistant, [nextQueuedItem]);
            yield break;
        }

        // When the caller did not supply a session, create one and use it for every inner call so
        // conversation history is preserved across auto-approval re-invocations. See the non-streaming
        // RunCoreAsync for details.
        session ??= await this.InnerAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        // 3. Stream from the inner agent in a loop. If all approval requests from the stream
        //    are auto-approved by standing rules, we immediately re-stream with the collected
        //    approval responses injected. This avoids returning empty streams.
        //
        //    Bounded by _maxAutoApprovalIterations for the same reason as the non-streaming path:
        //    every pass is a fresh inner invocation, so no per-request cap can bound it.
        for (int iteration = 0; ; iteration++)
        {
            // Inject any collected approval responses as a user message ahead of the caller's messages.
            var processedMessages = this.InjectCollectedResponses(callerMessages, state, session);

            if (iteration >= this._maxAutoApprovalIterations)
            {
                // Cap reached: take one final turn without auto-approving again. Updates are yielded
                // as-is, so any approval request reaches the caller to decide instead of continuing.
                // Those requests are recorded as surfaced so a legitimate always-approve response binds.
                bool recordedAnyCappedRequest = false;

                await foreach (var update in this.InnerAgent.RunStreamingAsync(processedMessages, session, options, cancellationToken).ConfigureAwait(false))
                {
                    // Record before yielding: a consumer may stop enumerating as soon as it sees an approval
                    // request, which disposes this iterator and skips anything after the loop. The record must
                    // already be persisted by the time the caller can act on the request.
                    List<ToolApprovalRequestContent>? cappedRequests = null;
                    foreach (var content in update.Contents)
                    {
                        if (content is ToolApprovalRequestContent cappedRequest)
                        {
                            (cappedRequests ??= []).Add(cappedRequest);
                        }
                    }

                    if (cappedRequests is not null)
                    {
                        // The first update carrying requests supersedes any earlier batch; later updates in this
                        // same turn add to it, since every one of them reaches the caller.
                        if (recordedAnyCappedRequest)
                        {
                            foreach (var cappedRequest in cappedRequests)
                            {
                                RecordSurfacedApprovalRequest(state, cappedRequest);
                            }
                        }
                        else
                        {
                            ResetSurfacedApprovalRequests(state, cappedRequests);
                            recordedAnyCappedRequest = true;
                        }

                        this._sessionState.SaveState(session, state);
                    }

                    yield return update;
                }

                yield break;
            }

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

            // 4. Classify the collected approval requests against standing rules and auto-approval rules.
            List<ToolApprovalRequestContent> unapproved = [];
            foreach (var tarc in streamedApprovalRequests)
            {
                if (MatchesRule(tarc, state.Rules, this._jsonSerializerOptions))
                {
                    state.CollectedApprovalResponses.Add(
                        tarc.CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
                }
                else if (await this.MatchesAutoApprovalRuleAsync(tarc, session, options, requestMessages).ConfigureAwait(false))
                {
                    state.CollectedApprovalResponses.Add(
                        tarc.CreateResponse(approved: true, reason: "Auto-approved by auto-approval rule"));
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
            //    Only the yielded request is recorded as surfaced; queued requests are recorded when
            //    they are later dequeued and presented.
            ResetSurfacedApprovalRequests(state, [unapproved[0]]);

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
    /// Records every <see cref="ToolApprovalRequestContent"/> found in the given messages as surfaced to the caller.
    /// </summary>
    /// <remarks>
    /// Used when a response is handed back without approval processing (the auto-approval cap path), where the
    /// requests still reach the caller and must therefore be bindable.
    /// </remarks>
    private void RecordSurfacedApprovalRequestsFromMessages(
        IList<ChatMessage> responseMessages,
        ToolApprovalState state,
        AgentSession? session)
    {
        List<ToolApprovalRequestContent>? requests = null;

        foreach (var message in responseMessages)
        {
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent request)
                {
                    (requests ??= []).Add(request);
                }
            }
        }

        if (requests is not null)
        {
            ResetSurfacedApprovalRequests(state, requests);
            this._sessionState.SaveState(session, state);
        }
    }

    /// <summary>
    /// Replaces the recorded set of surfaced approval requests with a new batch returned by the inner agent.
    /// A snapshot of each request is stored so later mutation of the caller-visible instance cannot change
    /// the recorded tool call used to bind the response.
    /// </summary>
    /// <remarks>
    /// A new batch from the inner agent supersedes any previous one, so stale entries from an abandoned
    /// approval cycle cannot later authorize a standing rule.
    /// <para>
    /// Request ids are unique by construction, so keying by id loses nothing: they derive from tool call ids, and
    /// inference services correlate a tool call to its result by that id alone. A duplicate id would already have
    /// broken that correlation upstream. Nothing a caller sends reaches this dictionary — every entry originates
    /// from the inner agent's own response — so a caller cannot manufacture a collision here.
    /// </para>
    /// </remarks>
    private static void ResetSurfacedApprovalRequests(ToolApprovalState state, IReadOnlyList<ToolApprovalRequestContent> requests)
    {
        state.SurfacedApprovalRequests.Clear();

        foreach (var request in requests)
        {
            state.SurfacedApprovalRequests[request.RequestId] = SnapshotRequest(request);
        }
    }

    /// <summary>
    /// Records a single approval request as surfaced to the caller, keyed by request id.
    /// </summary>
    /// <remarks>
    /// Used when dequeuing a previously queued request. Existing entries are preserved because every request in
    /// an in-flight queue cycle belongs to the same batch and may still be awaiting a response.
    /// </remarks>
    private static void RecordSurfacedApprovalRequest(ToolApprovalState state, ToolApprovalRequestContent request) =>
        state.SurfacedApprovalRequests[request.RequestId] = SnapshotRequest(request);

    /// <summary>
    /// Creates a snapshot of an approval request so a later mutation of the caller-visible instance
    /// (for example changing the tool call arguments) cannot alter the recorded request used for binding.
    /// </summary>
    private static ToolApprovalRequestContent SnapshotRequest(ToolApprovalRequestContent request)
    {
        if (request.ToolCall is FunctionCallContent functionCall)
        {
            var clonedCall = new FunctionCallContent(
                functionCall.CallId,
                functionCall.Name,
                functionCall.Arguments is null ? null : new Dictionary<string, object?>(functionCall.Arguments));

            return new ToolApprovalRequestContent(request.RequestId, clonedCall);
        }

        return request;
    }

    /// <summary>
    /// Re-evaluates queued approval requests against current rules and auto-approval rules, and auto-approves any that now match.
    /// </summary>
    private async ValueTask DrainAutoApprovableFromQueueAsync(
        ToolApprovalState state,
        AgentSession? session,
        AgentRunOptions? options,
        IReadOnlyCollection<ChatMessage> requestMessages)
    {
        for (int i = state.QueuedApprovalRequests.Count - 1; i >= 0; i--)
        {
            if (MatchesRule(state.QueuedApprovalRequests[i], state.Rules, this._jsonSerializerOptions))
            {
                state.CollectedApprovalResponses.Add(
                    state.QueuedApprovalRequests[i].CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
                state.QueuedApprovalRequests.RemoveAt(i);
            }
            else if (await this.MatchesAutoApprovalRuleAsync(state.QueuedApprovalRequests[i], session, options, requestMessages).ConfigureAwait(false))
            {
                state.CollectedApprovalResponses.Add(
                    state.QueuedApprovalRequests[i].CreateResponse(approved: true, reason: "Auto-approved by auto-approval rule"));
                state.QueuedApprovalRequests.RemoveAt(i);
            }
        }
    }

    /// <summary>
    /// Performs the common inbound processing shared by both the streaming and non-streaming paths:
    /// <list type="number">
    /// <item>Binds <see cref="AlwaysApproveToolApprovalResponseContent"/> wrappers to surfaced approval requests,
    /// extracting standing rules only from requests the harness actually issued.</item>
    /// <item>If there are queued approval requests from a previous batch, collects the caller's responses,
    /// drains any items now resolvable by new rules, and dequeues the next item if any remain.</item>
    /// </list>
    /// </summary>
    /// <returns>
    /// A tuple of (state, processed caller messages, next queued item or <see langword="null"/> if the queue is resolved).
    /// When the returned item is non-null, the caller should return/yield it without calling the inner agent.
    /// </returns>
    private async ValueTask<(ToolApprovalState State, List<ChatMessage> CallerMessages, ToolApprovalRequestContent? NextQueuedItem)>
        PrepareInboundMessagesAsync(IReadOnlyCollection<ChatMessage> messages, AgentSession? session, AgentRunOptions? options)
    {
        var state = this._sessionState.GetOrInitializeState(session);

        // During a queue cycle the caller's messages are not forwarded to the inner agent on this turn, so a bound
        // response must be collected into state instead of being left in the messages.
        bool queueCycleActive = state.QueuedApprovalRequests.Count > 0;

        // 1. Bind any approval responses in the caller's messages to a surfaced approval request.
        //    This consumes the matching request, extracts standing approval rules into state, and replaces
        //    wrappers with plain responses. An unbound response creates no rule and is forwarded as-is.
        var callerMessages = BindApprovalResponses(messages, state, this._jsonSerializerOptions, queueCycleActive);

        // 2. If there are queued approval requests from a previous batch, handle them
        //    before calling the inner agent.
        if (queueCycleActive)
        {
            // Re-evaluate remaining queued items — the caller may have added new rules
            // (e.g., "always approve this tool") that resolve additional items.
            await this.DrainAutoApprovableFromQueueAsync(state, session, options, messages).ConfigureAwait(false);

            if (state.QueuedApprovalRequests.Count > 0)
            {
                // More items remain — dequeue the next one for the caller.
                var next = state.QueuedApprovalRequests[0];
                state.QueuedApprovalRequests.RemoveAt(0);

                // Record it as surfaced only now that it is actually being presented, so a response cannot
                // be bound to a request the caller has not yet seen.
                RecordSurfacedApprovalRequest(state, next);

                this._sessionState.SaveState(session, state);
                return (state, callerMessages, next);
            }

            // Queue fully resolved — caller should proceed to call the inner agent.
            // Every request surfaced during this cycle must have been answered by now: the queue presents
            // one request at a time, each is recorded as surfaced only when presented and consumed when its
            // response arrives, and items auto-approved out of the queue were never surfaced at all. The
            // inner agent call that follows sends the whole batch to the inference service, which requires
            // every outstanding tool call to carry a result, so an unanswered surfaced request here is a
            // broken conversation rather than a state worth preserving.
            Debug.Assert(state.SurfacedApprovalRequests.Count == 0, "Surfaced approval requests should be empty once the queue is resolved.");

            this._sessionState.SaveState(session, state);
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
    private async ValueTask<bool> ProcessAndQueueOutboundApprovalRequestsAsync(
        IList<ChatMessage> responseMessages,
        ToolApprovalState state,
        AgentSession? session,
        AgentRunOptions? options,
        IReadOnlyCollection<ChatMessage> requestMessages)
    {
        // Pass 1: Scan all response messages and classify each approval request.
        //         Auto-approved requests (matching a standing rule or auto-approval rule) have their
        //         responses collected immediately, preserving the original request order, and are
        //         marked for removal. Unapproved requests are collected for the caller to decide.
        var toRemove = new HashSet<ToolApprovalRequestContent>();
        var unapproved = new List<ToolApprovalRequestContent>();
        int autoApprovedCount = 0;

        foreach (var message in responseMessages)
        {
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent tarc)
                {
                    if (MatchesRule(tarc, state.Rules, this._jsonSerializerOptions))
                    {
                        state.CollectedApprovalResponses.Add(
                            tarc.CreateResponse(approved: true, reason: "Auto-approved by standing rule"));
                        toRemove.Add(tarc);
                        autoApprovedCount++;
                    }
                    else if (await this.MatchesAutoApprovalRuleAsync(tarc, session, options, requestMessages).ConfigureAwait(false))
                    {
                        state.CollectedApprovalResponses.Add(
                            tarc.CreateResponse(approved: true, reason: "Auto-approved by auto-approval rule"));
                        toRemove.Add(tarc);
                        autoApprovedCount++;
                    }
                    else
                    {
                        unapproved.Add(tarc);
                    }
                }
            }
        }

        // Nothing to process: no auto-approved items and at most one unapproved (no queueing needed).
        if (autoApprovedCount == 0 && unapproved.Count <= 1)
        {
            // The single unapproved request is still returned to the caller, so record it as surfaced.
            // Without this, a legitimate always-approve response to it could not be bound.
            if (unapproved.Count == 1)
            {
                ResetSurfacedApprovalRequests(state, unapproved);
                this._sessionState.SaveState(session, state);
            }

            return false;
        }

        // If every approval request was auto-approved, strip them all and signal the caller
        // to re-invoke the inner agent immediately with the collected responses.
        if (unapproved.Count == 0)
        {
            RemoveAllToolApprovalRequests(responseMessages);
            this._sessionState.SaveState(session, state);
            return true;
        }

        // Only the first unapproved request is returned to the caller now, so only it is surfaced.
        // Queued requests are recorded when they are later dequeued and presented.
        ResetSurfacedApprovalRequests(state, [unapproved[0]]);

        // Pass 2: Keep only the first unapproved request in the response (for the caller to decide).
        //         Queue the remaining unapproved requests for subsequent one-at-a-time delivery.
        //         Remove all auto-approved and queued items from the response messages.
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
    /// Scans input messages for tool approval responses — plain <see cref="ToolApprovalResponseContent"/> and
    /// <see cref="AlwaysApproveToolApprovalResponseContent"/> wrappers alike — and binds each one to an approval
    /// request the harness actually surfaced, before any standing rule is recorded.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A response is bound only when its request id matches a request recorded in
    /// <see cref="ToolApprovalState.SurfacedApprovalRequests"/>. The matched request is consumed, and both the
    /// forwarded response and any standing rule are derived from the <b>recorded</b> tool call rather than from the
    /// caller-supplied one, so a caller cannot widen an approval by substituting a different tool name or arguments.
    /// </para>
    /// <para>
    /// This is the single place a surfaced request is consumed, and it runs on every inbound pass. Plain responses
    /// must consume their request too: otherwise a request answered once would stay eligible for binding, letting a
    /// caller replay the same id as a wrapper to promote a one-time approval into a standing rule, or to overturn a
    /// denial with an approval.
    /// </para>
    /// <para>
    /// A response that cannot be bound creates no standing rule. A wrapper is downgraded to the plain approval
    /// response it carries, and a plain response is forwarded unchanged, for the approval binding chat client to
    /// validate against its own record. This is deliberate: an unbound response is produced both by a forgery and by
    /// legitimate cases such as replaying a transcript into a new session, so the two are treated identically and
    /// safely rather than one of them failing the run. Unbound responses are never dropped here.
    /// </para>
    /// <para>
    /// Only a wrapper can create a standing rule, and only when it carries an approval.
    /// </para>
    /// </remarks>
    /// <param name="messages">The caller's inbound messages.</param>
    /// <param name="state">The tool approval state for the session.</param>
    /// <param name="jsonSerializerOptions">Options used to serialize arguments for exact-argument rules.</param>
    /// <param name="collectBoundResponses">
    /// When <see langword="true"/>, a bound response is moved into <see cref="ToolApprovalState.CollectedApprovalResponses"/>
    /// for injection once the queue resolves, instead of being left in the messages. Used during a queue cycle, where
    /// the caller's messages are not forwarded to the inner agent on this turn.
    /// </param>
    private static List<ChatMessage> BindApprovalResponses(
        IEnumerable<ChatMessage> messages,
        ToolApprovalState state,
        JsonSerializerOptions jsonSerializerOptions,
        bool collectBoundResponses)
    {
        var messageList = messages as IList<ChatMessage> ?? [.. messages];
        var result = new List<ChatMessage>(messageList.Count);
        bool anyModified = false;

        foreach (var message in messageList)
        {
            // Quick check: does this message contain any approval response at all, wrapped or plain?
            bool hasApprovalResponse = false;
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalResponseContent or AlwaysApproveToolApprovalResponseContent)
                {
                    hasApprovalResponse = true;
                    break;
                }
            }

            if (!hasApprovalResponse)
            {
                result.Add(message);
                continue;
            }

            // Walk content items, binding each approval response to a surfaced request before
            // recording any standing rule.
            var newContents = new List<AIContent>(message.Contents.Count);
            foreach (var content in message.Contents)
            {
                // Unwrap so plain and wrapped responses share one binding decision. Only a wrapper can
                // carry a standing rule, so the wrapper itself is kept to consult its flags after binding.
                var alwaysApprove = content as AlwaysApproveToolApprovalResponseContent;
                var innerResponse = alwaysApprove?.InnerResponse ?? content as ToolApprovalResponseContent;

                if (innerResponse is null)
                {
                    newContents.Add(content);
                    continue;
                }

                // Security boundary: an approval may only be honored against a request this agent surfaced and is
                // still awaiting a response for. Remove on match so a surfaced request authorizes at most one
                // response; without this a one-time approval could be replayed as a wrapper and silently promoted
                // to a standing rule, and a denied request could be re-answered with an approval.
                //
                // An unmatched response is NOT an error. It legitimately occurs when a transcript is replayed to
                // re-seed a new session, when a stateless caller resends history, or when no session store is
                // configured. It is also what a forged response looks like. The two are indistinguishable from here,
                // so both are handled the same safe way: no standing rule is created, and a wrapper is downgraded
                // to the plain approval response it carries. That response is not honored here either; it is
                // forwarded unchanged for ApprovalResponseBindingChatClient to validate against its own record.
                if (!state.SurfacedApprovalRequests.TryGetValue(innerResponse.RequestId, out var surfacedRequest))
                {
                    newContents.Add(innerResponse);
                    continue;
                }

                state.SurfacedApprovalRequests.Remove(innerResponse.RequestId);

                // Rebind to the recorded tool call so the approved call is exactly what was surfaced.
                var boundResponse = new ToolApprovalResponseContent(
                    innerResponse.RequestId,
                    innerResponse.Approved,
                    surfacedRequest.ToolCall)
                {
                    Reason = innerResponse.Reason,
                };

                // Only an approval carried by a wrapper creates a standing rule. A denial, or a plain response
                // answering only this one request, is a legitimate answer that records nothing.
                if (alwaysApprove is not null && innerResponse.Approved && surfacedRequest.ToolCall is FunctionCallContent recordedCall)
                {
                    if (alwaysApprove.AlwaysApproveTool)
                    {
                        AddRuleIfNotExists(state, new ToolApprovalRule { ToolName = recordedCall.Name });
                    }
                    else if (alwaysApprove.AlwaysApproveToolWithArguments)
                    {
                        AddRuleIfNotExists(state, new ToolApprovalRule
                        {
                            ToolName = recordedCall.Name,
                            Arguments = SerializeArguments(recordedCall.Arguments, jsonSerializerOptions),
                        });
                    }
                }

                if (collectBoundResponses)
                {
                    // Queue cycle: hold the response for injection once every queued request is resolved.
                    state.CollectedApprovalResponses.Add(boundResponse);
                }
                else
                {
                    // Replace the response with the bound one, preserving position.
                    newContents.Add(boundResponse);
                }
            }

            // Clone the original message so all metadata is preserved, then replace contents.
            // A message left empty by collecting its responses is dropped.
            if (newContents.Count > 0)
            {
                var clonedMessage = message.Clone();
                clonedMessage.Contents = newContents;
                result.Add(clonedMessage);
            }

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
    /// Checks whether a <see cref="ToolApprovalRequestContent"/> is approved by any of the configured
    /// auto-approval rules (heuristic functions).
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if any auto-approval rule returns <see langword="true"/> for the function call;
    /// <see langword="false"/> if no rules are configured, the request is not a function call, or no rule approves it.
    /// </returns>
    private async ValueTask<bool> MatchesAutoApprovalRuleAsync(
        ToolApprovalRequestContent request,
        AgentSession? session,
        AgentRunOptions? options,
        IReadOnlyCollection<ChatMessage> requestMessages)
    {
        if (this._autoApprovalRules is not { Length: > 0 })
        {
            return false;
        }

        if (request.ToolCall is not FunctionCallContent functionCall)
        {
            return false;
        }

        var context = new ToolAutoApprovalRuleContext(functionCall, this, session, requestMessages, options);

        foreach (var rule in this._autoApprovalRules)
        {
            if (await rule(context).ConfigureAwait(false))
            {
                return true;
            }
        }

        return false;
    }

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
    /// <remarks>
    /// Always returns a non-null dictionary so that an argument-scoped standing approval
    /// (the <see cref="AlwaysApproveToolApprovalResponseContent.AlwaysApproveToolWithArguments"/>
    /// path) records an exact-arguments rule. A <see langword="null"/> or empty source dictionary
    /// yields an empty dictionary, which matches only future no-argument calls. A <see langword="null"/>
    /// value is reserved on <see cref="ToolApprovalRule.Arguments"/> for tool-level rules and is never
    /// produced here, preventing an exact-arguments approval from widening into a tool-level approval.
    /// </remarks>
    private static Dictionary<string, string> SerializeArguments(IDictionary<string, object?>? arguments, JsonSerializerOptions jsonSerializerOptions)
    {
        if (arguments is null || arguments.Count == 0)
        {
            return new Dictionary<string, string>(StringComparer.Ordinal);
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
