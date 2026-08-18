// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface ISuperStepRunner
{
    string SessionId { get; }

    string StartExecutorId { get; }

    WorkflowTelemetryContext TelemetryContext { get; }

    bool HasUnservicedRequests { get; }
    bool HasUnprocessedMessages { get; }

    ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default);
    bool TryGetResponsePortExecutorId(string portId, out string? executorId);

    ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellationToken = default);
    ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellationToken = default);
    ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType, CancellationToken cancellationToken = default);

    ConcurrentEventSink OutgoingEvents { get; }

    /// <summary>
    /// Re-emits <see cref="RequestInfoEvent"/>s for any pending external requests.
    /// Called by event streams after subscribing to <see cref="OutgoingEvents"/> so that
    /// requests restored from a checkpoint are observable even when the restore happened
    /// before the subscription was active.
    /// </summary>
    ValueTask RepublishPendingEventsAsync(CancellationToken cancellationToken = default);

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellationToken);

    // This cannot be cancelled
    ValueTask RequestEndRunAsync();
}
