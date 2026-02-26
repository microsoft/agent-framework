// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal static class ExecutionExtensions
{
    public static InProcessExecutionEnvironment ToWorkflowExecutionEnvironment(this ExecutionEnvironment environment)
    {
        return environment switch
        {
            ExecutionEnvironment.InProcess_OffThread => InProcessExecution.OffThread,
            ExecutionEnvironment.InProcess_Lockstep => InProcessExecution.Lockstep,
            ExecutionEnvironment.InProcess_Concurrent => InProcessExecution.Concurrent,

            _ => throw new InvalidOperationException($"Unknown execution environment {environment}")
        };
    }
}
