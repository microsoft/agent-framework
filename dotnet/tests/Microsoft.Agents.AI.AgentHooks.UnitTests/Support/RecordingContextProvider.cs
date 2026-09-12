// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>A context provider that records its run-end (durable) notifications and failure notifications.</summary>
internal sealed class RecordingContextProvider : AIContextProvider
{
    public List<ChatMessage> StoredResponses { get; } = [];

    public List<(Exception Exception, int RequestMessageCount)> FailureNotifications { get; } = [];

    public int StoreCalls;

    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        new(new AIContext());

    protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            this.FailureNotifications.Add((context.InvokeException, context.RequestMessages.Count()));
        }

        return base.InvokedCoreAsync(context, cancellationToken);
    }

    protected override ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Interlocked.Increment(ref this.StoreCalls);
        this.StoredResponses.AddRange(context.ResponseMessages ?? []);
        return default;
    }
}
