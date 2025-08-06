// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// .
/// </summary>
public static class WorkflowBuilderExtensions
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="source"></param>
    /// <param name="executors"></param>
    /// <returns></returns>
    /// <exception cref="ArgumentException"></exception>
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

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="builder"></param>
    /// <param name="outputSource"></param>
    /// <param name="aggregator"></param>
    /// <returns></returns>
    public static Workflow<TInput, TResult> BuildWithOutput<TInput, TResult>(this WorkflowBuilder builder, ExecutorIsh outputSource, StreamingAggregator<TResult, TResult> aggregator)
        => builder.BuildWithOutput<TInput, TResult, TResult>(outputSource, aggregator);

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TIntermediate"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="builder"></param>
    /// <param name="outputSource"></param>
    /// <param name="aggregator"></param>
    /// <returns></returns>
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
}
