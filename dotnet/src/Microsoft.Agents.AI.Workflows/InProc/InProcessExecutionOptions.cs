// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.InProc;

internal class InProcessExecutionOptions
{
    public ExecutionMode ExecutionMode { get; init; } = InProcessExecution.Default.ExecutionMode;

    public bool AllowSharedWorkflow { get; init; }
}
