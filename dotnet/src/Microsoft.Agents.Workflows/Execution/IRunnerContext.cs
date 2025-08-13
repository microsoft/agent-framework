// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal interface IRunnerContext : IExternalRequestSink
{
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);
    ValueTask SendMessageAsync(string executorId, object message);

    // TODO: State Management

    StepContext Advance();
    IWorkflowContext Bind(string executorId);
    ValueTask<Executor> EnsureExecutorAsync(string executorId);
}
