// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal interface IRunnerContext
{
    ValueTask AddEventAsync(string executorId, WorkflowEvent workflowEvent);
    ValueTask SendMessageAsync(string executorId, object message);

    // TODO: State Management

    StepContext Advance();
    IWorkflowContext Bind(string executorId);
    ValueTask<Executor> EnsureExecutorAsync(string executorId);
}
