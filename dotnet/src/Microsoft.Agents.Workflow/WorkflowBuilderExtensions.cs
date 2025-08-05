// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Core;
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

        HashSet<string> seenExecutors = new();
        seenExecutors.Add(source.Id);

        for (int i = 0; i < executors.Length; i++)
        {
            Throw.IfNull(executors[i], nameof(executors) + $"[{i}]");

            if (seenExecutors.Contains(executors[i].Id))
            {
                throw new ArgumentException($"Executor '{executors[i].Id}' is already in the chain.", nameof(executors));
            }
            seenExecutors.Add(executors[i].Id);

            builder.AddEdge(source, executors[i]);
            source = executors[i];
        }

        return builder;
    }

    public static Workflow<TInput, TResult> BuildWithOutput<TInput, TResult>(this WorkflowBuilder builder, ExecutorIsh outputSource, StreamingAggregator<TResult, TResult> aggregator)
        => builder.BuildWithOutput<TInput, TResult, TResult>(outputSource, aggregator);

    public static Workflow<TInput, TResult> BuildWithOutput<TInput, TIntermediate, TResult>(this WorkflowBuilder builder, ExecutorIsh outputSource, StreamingAggregator<TIntermediate, TResult> aggregator)
    {
        Throw.IfNull(outputSource);
        Throw.IfNull(aggregator);

        OutputCollectorExecutor<TIntermediate, TResult> outputSink = new(aggregator);

        // TODO: Check taht the outputSource has a TResult output?
        builder.AddEdge(outputSource, outputSink);

        Workflow<TInput> workflow = builder.Build<TInput>();
        return workflow.Promote(outputSink);
    }

    //public static WorkflowBuilder AddMapReduce
}

//class T
//{
//    async Task A()
//    {
//        WorkflowBuilder b;

//        Workflow<int, IEnumerable<string>> wf =
//            WorkflowBuilderExtensions.BuildWithOutput<int, string, IEnumerable<string>>(b, "my_last_node", StreamingAggregators.Union<string>());

//        LocalRunner<int, IEnumerable<string>> runner = new(wf);

//        await runner.RunAsync(42).ConfigureAwait(false);
//        var result = runner.RunningOutput;
//    }
//}
