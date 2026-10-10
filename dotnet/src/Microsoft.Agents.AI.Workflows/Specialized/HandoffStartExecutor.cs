// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal static class HandoffConstants
{
    internal const string HandoffOrchestrationSharedScope = "HandoffOrchestration";

    internal const string PreviousAgentTrackerKey = "LastAgentId";
    internal const string PreviousAgentTrackerScope = HandoffOrchestrationSharedScope;

    internal const string MultiPartyConversationKey = "MultiPartyConversation";
    internal const string MultiPartyConversationScope = HandoffOrchestrationSharedScope;

    internal const string HandoffSharedStateKey = "SharedState";
    internal const string HandoffSharedStateScope = HandoffOrchestrationSharedScope;
}

internal sealed class HandoffSharedState
{
    [JsonConstructor]
    internal HandoffSharedState(MultiPartyConversation conversation, string? previousAgentId, Dictionary<string, int>? autonomousTurnsByAgent, bool isTurnInProgress = false)
    {
        this.Conversation = conversation;
        this.PreviousAgentId = previousAgentId;
        this.AutonomousTurnsByAgent = autonomousTurnsByAgent ?? [];
        this.IsTurnInProgress = isTurnInProgress;
    }

    public HandoffSharedState()
    {
        this.Conversation = new([]);
        this.AutonomousTurnsByAgent = [];
    }

    [JsonInclude]
    public MultiPartyConversation Conversation { get; internal set; }

    public string? PreviousAgentId { get; set; }

    /// <summary>
    /// Tracks the number of autonomous-mode continuation iterations consumed by each agent in the current
    /// "active" autonomous run. The counter is incremented by <see cref="HandoffEndExecutor"/> each time
    /// the End executor loops control back to the source agent in autonomous mode, and reset to 0 once
    /// the autonomous loop terminates (limit reached or termination condition fired).
    /// </summary>
    [JsonInclude]
    public Dictionary<string, int> AutonomousTurnsByAgent { get; internal set; }

    /// <summary>
    /// Whether a turn started by <see cref="HandoffStartExecutor"/> has not yet reached <see cref="HandoffEndExecutor"/>.
    /// A turn holding a pending request stays in progress until the response resumes and completes it.
    /// </summary>
    [JsonInclude]
    public bool IsTurnInProgress { get; internal set; }
}

/// <summary>Executor used at the start of a handoffs workflow to accumulate messages and emit them as HandoffState upon receiving a turn token.</summary>
internal sealed class HandoffStartExecutor(bool returnToPrevious) : ChatProtocolExecutor(ExecutorId, DefaultOptions, declareCrossRunShareable: true), IResettableExecutor
{
    internal const string ExecutorId = "HandoffStart";

    private static ChatProtocolExecutorOptions DefaultOptions => new()
    {
        StringMessageChatRole = ChatRole.User,
        AutoSendTurnToken = false
    };

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        base.ConfigureProtocol(protocolBuilder).SendsMessage<HandoffState>();

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        // WorkflowSession sends a turn token on every resume, including a resume that only answers a request held
        // by an agent executor. That executor continues the turn it holds, so a second, empty turn is not started
        // alongside it: both would write the shared state in the same superstep. A turn token without messages
        // while no turn is in progress is a run with no new input, and starts a turn as usual.
        if (messages.Count == 0)
        {
            HandoffSharedState? currentState = await context.ReadStateAsync<HandoffSharedState>(
                HandoffConstants.HandoffSharedStateKey, HandoffConstants.HandoffSharedStateScope, cancellationToken).ConfigureAwait(false);

            if (currentState?.IsTurnInProgress == true)
            {
                return;
            }
        }

        await context.InvokeWithStateAsync(
            async (HandoffSharedState? sharedState, IWorkflowContext context, CancellationToken cancellationToken) =>
            {
                sharedState ??= new HandoffSharedState();
                sharedState.IsTurnInProgress = true;
                sharedState.Conversation.AddMessages(messages);

                // Reset all autonomous-mode counters at the start of every fresh user turn so that a
                // prior turn's counters cannot prematurely terminate the new turn's autonomous loop.
                sharedState.AutonomousTurnsByAgent.Clear();

                string? previousAgentId = sharedState.PreviousAgentId;

                // If we are configured to return to the previous agent, include the previous agent id in the handoff state.
                // If there was no previousAgent, it will still be null.
                HandoffState turnState = new(new(emitEvents), null, returnToPrevious ? previousAgentId : null);

                await context.SendMessageAsync(turnState, cancellationToken).ConfigureAwait(false);

                return sharedState;
            },
            HandoffConstants.HandoffSharedStateKey,
            HandoffConstants.HandoffSharedStateScope,
            cancellationToken).ConfigureAwait(false);
    }

    public new ValueTask ResetAsync() => base.ResetAsync();
}
