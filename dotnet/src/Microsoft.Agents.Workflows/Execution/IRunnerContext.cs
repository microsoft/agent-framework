// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal interface IRunnerContext : IExternalRequestSink
{
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);
    ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null);

    ValueTask<StepContext> AdvanceAsync();
    IWorkflowContext Bind(string executorId);
    ValueTask<Executor> EnsureExecutorAsync(string executorId, IStepTracer? tracer);
}
