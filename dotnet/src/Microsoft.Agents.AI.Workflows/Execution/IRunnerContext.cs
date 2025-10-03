// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IRunnerContext : IExternalRequestSink, ISuperStepJoinContext
{
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);
    ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null);

    ValueTask<StepContext> AdvanceAsync();
    IWorkflowContext Bind(string executorId, Dictionary<string, string>? traceContext = null);
    ValueTask<Executor> EnsureExecutorAsync(string executorId, IStepTracer? tracer);
}
