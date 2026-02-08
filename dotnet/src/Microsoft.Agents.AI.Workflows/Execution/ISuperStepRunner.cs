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

    ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default);

    ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellationToken = default);
    ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellationToken = default);
    ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType, CancellationToken cancellationToken = default);

    ConcurrentEventSink OutgoingEvents { get; }

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellationToken);

    // This cannot be cancelled
    ValueTask RequestEndRunAsync();
}
