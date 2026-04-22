// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
    public MultiPartyConversation Conversation { get; } = new();

    public string? PreviousAgentId { get; set; }
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

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        return context.InvokeWithStateAsync(
            async (HandoffSharedState? sharedState, IWorkflowContext context, CancellationToken cancellationToken) =>
            {
                sharedState ??= new HandoffSharedState();
                sharedState.Conversation.AddMessages(messages);

                string? previousAgentId = sharedState.PreviousAgentId;

                // If we are configured to return to the previous agent, include the previous agent id in the handoff state.
                // If there was no previousAgent, it will still be null.
                HandoffState turnState = new(new(emitEvents), null, returnToPrevious ? previousAgentId : null);

                await context.SendMessageAsync(turnState, cancellationToken).ConfigureAwait(false);

                return sharedState;
            },
            HandoffConstants.HandoffSharedStateKey,
            HandoffConstants.HandoffSharedStateScope,
            cancellationToken);
    }

    public new ValueTask ResetAsync() => base.ResetAsync();
}
