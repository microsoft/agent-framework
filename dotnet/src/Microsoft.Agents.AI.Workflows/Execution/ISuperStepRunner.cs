// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface ISuperStepRunner
{
    string RunId { get; }

    string StartExecutorId { get; }

    bool HasUnservicedRequests { get; }
    bool HasUnprocessedMessages { get; }

    ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellation = default);

    ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellation = default);
    ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellation = default);
    ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType, CancellationToken cancellation = default);

    ConcurrentEventSink OutgoingEvents { get; }

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellationToken);

    // This cannot be cancelled
    ValueTask RequestEndRunAsync();
}
