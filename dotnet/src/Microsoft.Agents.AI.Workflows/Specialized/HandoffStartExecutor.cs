// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal static class HandoffConstants
{
    internal const string PreviousAgentTrackerKey = "LastAgentId";
    internal const string PreviousAgentTrackerScope = "HandoffOrchestration";
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
        if (returnToPrevious)
        {
            return context.InvokeWithStateAsync(
                async (string? previousAgentId, IWorkflowContext context, CancellationToken cancellationToken) =>
                {
                    HandoffState handoffState = new(new(emitEvents), null, messages, previousAgentId);
                    await context.SendMessageAsync(handoffState, cancellationToken).ConfigureAwait(false);

                    return previousAgentId;
                },
                HandoffConstants.PreviousAgentTrackerKey,
                HandoffConstants.PreviousAgentTrackerScope,
                cancellationToken);
        }

        HandoffState handoff = new(new(emitEvents), null, messages);
        return context.SendMessageAsync(handoff, cancellationToken);
    }

    public new ValueTask ResetAsync() => base.ResetAsync();
}
