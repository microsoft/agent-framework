// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IRunnerContext : IExternalRequestSink, ISuperStepJoinContext
{
    ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default);
    ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null, CancellationToken cancellationToken = default);

    ValueTask<StepContext> AdvanceAsync(CancellationToken cancellationToken = default);
    IWorkflowContext Bind(string executorId, Dictionary<string, string>? traceContext = null);
    ValueTask<Executor> EnsureExecutorAsync(string executorId, IStepTracer? tracer, CancellationToken cancellationToken = default);
}
