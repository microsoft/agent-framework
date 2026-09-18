// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>A chat history provider that records exactly what becomes durable (and what failure notifications carry).</summary>
internal sealed class RecordingHistoryProvider : ChatHistoryProvider
{
    public List<ChatMessage> Stored { get; } = [];

    public List<(Exception Exception, int RequestMessageCount)> FailureNotifications { get; } = [];

    public int StoreCalls;

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        new([.. this.Stored]);

    protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            this.FailureNotifications.Add((context.InvokeException, context.RequestMessages.Count()));
        }

        return base.InvokedCoreAsync(context, cancellationToken);
    }

    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Interlocked.Increment(ref this.StoreCalls);
        this.Stored.AddRange(context.RequestMessages);
        this.Stored.AddRange(context.ResponseMessages ?? []);
        return default;
    }
}
