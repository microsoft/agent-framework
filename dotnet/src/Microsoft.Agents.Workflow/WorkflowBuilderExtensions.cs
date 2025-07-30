// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

internal static class WorkflowBuilderExtensions
{
    public static WorkflowBuilder AddLoop(this WorkflowBuilder builder, ExecutorIsh source, ExecutorIsh loopBody, Func<object?, bool>? condition = null)
    {
        Throw.IfNull(builder);
        Throw.IfNull(source);
        Throw.IfNull(loopBody);

        builder.AddEdge(source, loopBody, condition);
        builder.AddEdge(loopBody, source);

        return builder;
    }

    public static WorkflowBuilder AddChain(this WorkflowBuilder builder, ExecutorIsh source, params ExecutorIsh[] executors)
    {
        Throw.IfNull(builder);
        Throw.IfNull(source);

        for (int i = 0; i < executors.Length; i++)
        {
            Throw.IfNull(executors[i], nameof(executors) + $"[{i}]");
            builder.AddEdge(source, executors[i]);
            source = executors[i];
        }

        return builder;
    }
}
