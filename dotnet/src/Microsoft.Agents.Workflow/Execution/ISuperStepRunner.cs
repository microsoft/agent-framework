// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal interface ISuperStepRunner
{
    ValueTask EnqueueMessageAsync(object message);

    event EventHandler<WorkflowEvent>? WorkflowEvent;

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellation);
}
