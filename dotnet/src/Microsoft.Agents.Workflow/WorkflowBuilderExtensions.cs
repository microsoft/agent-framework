// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Specialized;
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
    /// <typeparam name="TRequest"></typeparam>
    /// <typeparam name="TResponse"></typeparam>
    /// <param name="builder"></param>
    /// <param name="source"></param>
    /// <param name="portId"></param>
    /// <returns></returns>
    public static WorkflowBuilder AddExternalCall<TRequest, TResponse>(this WorkflowBuilder builder, ExecutorIsh source, string portId)
    {
        Throw.IfNull(builder);
        Throw.IfNull(source);
        Throw.IfNull(portId);

        InputPort port = new(portId, typeof(TRequest), typeof(TResponse));
        return builder.AddEdge(source, port)
                      .AddEdge(port, source);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="builder"></param>
    /// <param name="outputSource"></param>
    /// <param name="aggregator"></param>
    /// <param name="completionCondition"></param>
    /// <returns></returns>
    public static Workflow<TInput, TResult> BuildWithOutput<TInput, TResult>(
        this WorkflowBuilder builder,
        ExecutorIsh outputSource,
        StreamingAggregator<TInput, TResult> aggregator,
        Func<TInput, TResult?, bool>? completionCondition = null)
    {
        Throw.IfNull(outputSource);
        Throw.IfNull(aggregator);

        OutputCollectorExecutor<TInput, TResult> outputSink = new(aggregator, completionCondition);

        // TODO: Check taht the outputSource has a TResult output?
        builder.AddEdge(outputSource, outputSink);

        Workflow<TInput> workflow = builder.Build<TInput>();
        return workflow.Promote(outputSink);
    }
}
