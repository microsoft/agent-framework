// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal static class ExecutionExtensions
{
    public static IWorkflowExecutionEnvironment ToWorkflowExecutionEnvironment(this ExecutionEnvironment environment)
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
