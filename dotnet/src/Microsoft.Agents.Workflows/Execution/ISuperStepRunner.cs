// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal interface ISuperStepRunner
{
    bool HasUnservicedRequests { get; }
    bool HasUnprocessedMessages { get; }

    ValueTask EnqueueMessageAsync(object message);

    event EventHandler<WorkflowEvent>? WorkflowEvent;

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellation);
}
