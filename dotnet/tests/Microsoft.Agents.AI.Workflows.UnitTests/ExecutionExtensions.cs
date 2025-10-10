// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal static class ExecutionExtensions
{
    public static InProcessExecutionEnvironment GetEnvironment(this ExecutionMode executionMode)
    {
        return executionMode switch
        {
            ExecutionMode.OffThread => InProcessExecution.OffThread,
            ExecutionMode.Lockstep => InProcessExecution.Lockstep,
            ExecutionMode.Subworkflow => throw new NotSupportedException(),
            _ => throw new InvalidOperationException($"Unknown execution mode {executionMode}")
        };
    }
}
