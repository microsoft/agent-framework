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

    ValueTask EnqueueResponseAsync(ExternalResponse response);
    ValueTask<bool> EnqueueMessageAsync<T>(T message);
    ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType);

    event EventHandler<WorkflowEvent>? WorkflowEvent;

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellationToken);

    ValueTask RequestEndRunAsync();
}
