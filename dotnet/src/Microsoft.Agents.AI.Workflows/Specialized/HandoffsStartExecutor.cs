// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the start of a handoffs workflow to accumulate messages and emit them as HandoffState upon receiving a turn token.</summary>
internal sealed class HandoffsStartExecutor() : ChatProtocolExecutor(ExecutorId, DefaultOptions, declareCrossRunShareable: true), IResettableExecutor
{
    internal const string ExecutorId = "HandoffStart";

    private static ChatProtocolExecutorOptions DefaultOptions => new()
    {
        StringMessageChatRole = ChatRole.User
    };

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => context.SendMessageAsync(new HandoffState(new(emitEvents), null, messages), cancellationToken: cancellationToken);

    public new ValueTask ResetAsync() => base.ResetAsync();
}
