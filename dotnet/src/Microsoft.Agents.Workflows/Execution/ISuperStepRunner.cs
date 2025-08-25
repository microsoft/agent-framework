// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal interface ISuperStepRunner
{
    bool HasUnservicedRequests { get; }
    bool HasUnprocessedMessages { get; }

    ValueTask EnqueueResponseAsync(ExternalResponse response);
    ValueTask<bool> EnqueueMessageAsync<T>(T message);

    event EventHandler<WorkflowEvent>? WorkflowEvent;

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellation);
}
