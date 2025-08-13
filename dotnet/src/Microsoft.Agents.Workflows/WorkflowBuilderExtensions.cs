﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides extension methods for configuring and building workflows using the WorkflowBuilder type.
/// </summary>
/// <remarks>These extension methods simplify the process of connecting executors, adding external calls, and
/// constructing workflows with output aggregation. They are intended to streamline workflow graph construction and
/// promote common patterns for chaining and aggregating workflow steps.</remarks>
public static class WorkflowBuilderExtensions
{
    /// <summary>
    /// Adds a sequential chain of executors to the workflow, connecting each executor in order so that each is
    /// executed after the previous one.
    /// </summary>
    /// <remarks>Each executor in the chain is connected so that execution flows from the source to each subsequent
    /// executor in the order provided.</remarks>
    /// <param name="builder">The workflow builder to which the executor chain will be added. </param>
    /// <param name="source">The initial executor in the chain. Cannot be null.</param>
    /// <param name="executors">An ordered array of executors to be added to the chain after the source.</param>
    /// <returns>The original workflow builder instance with the specified executor chain added.</returns>
    /// <exception cref="ArgumentException">Thrown if there is a cycle in the chain.</exception>
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
    /// Adds an external call to the workflow by connecting the specified source to a new input port with the given
    /// request and response types.
    /// </summary>
    /// <remarks>This method creates a bidirectional connection between the source and the new input port,
    /// allowing the workflow to send requests and receive responses through the specified external call. The port is
    /// configured to handle messages of the specified request and response types.</remarks>
    /// <typeparam name="TRequest">The type of the request message that the external call will accept.</typeparam>
    /// <typeparam name="TResponse">The type of the response message that the external call will produce.</typeparam>
    /// <param name="builder">The workflow builder to which the external call will be added. </param>
    /// <param name="source">The source executor representing the external system or process to connect. Cannot be null.</param>
    /// <param name="portId">The unique identifier for the input port that will handle the external call. Cannot be null.</param>
    /// <returns>The original workflow builder instance with the external call added.</returns>
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
    /// Adds a switch step to the workflow, allowing conditional branching based on the specified source executor.
    /// </summary>
    /// <remarks>Use this method to introduce conditional logic into a workflow, enabling execution to follow
    /// different paths based on the outcome of the source executor. The switch configuration defines the available
    /// branches and their associated conditions.</remarks>
    /// <param name="builder">The workflow builder to which the switch step will be added. Cannot be null.</param>
    /// <param name="source">The source executor that determines the branching condition for the switch. Cannot be null.</param>
    /// <param name="configureSwitch">An action used to configure the switch builder, specifying the branches and their conditions. Cannot be null.</param>
    /// <returns>The workflow builder instance with the configured switch step added.</returns>
    public static WorkflowBuilder AddSwitch(this WorkflowBuilder builder, ExecutorIsh source, Action<SwitchBuilder> configureSwitch)
    {
        Throw.IfNull(builder);
        Throw.IfNull(source);
        Throw.IfNull(configureSwitch);

        SwitchBuilder switchBuilder = new();
        configureSwitch(switchBuilder);

        return switchBuilder.ReduceToFanOut(builder, source);
    }

    /// <summary>
    /// Builds a workflow that collects output from the specified executor, aggregates results using the provided
    /// streaming aggregator, and optionally completes based on a custom condition.
    /// </summary>
    /// <remarks>The returned workflow promotes the output collector as its result source, allowing consumers
    /// to access the aggregated output directly. The completion condition can be used to implement custom termination
    /// logic, such as early stopping when a desired result is reached.</remarks>
    /// <typeparam name="TInput">The type of input items processed by the workflow.</typeparam>
    /// <typeparam name="TResult">The type of aggregated result produced by the workflow.</typeparam>
    /// <param name="builder">The workflow builder used to construct the workflow and define its execution graph.</param>
    /// <param name="outputSource">The executor that produces output items to be collected and aggregated. Cannot be null.</param>
    /// <param name="aggregator">The streaming aggregator that processes input items and produces aggregated results. Cannot be null.</param>
    /// <param name="completionCondition">An optional predicate that determines when the workflow should complete based on the current input and
    /// aggregated result. If null, the workflow will not raise a <see cref="WorkflowCompletedEvent"/>.</param>
    /// <returns>A workflow that collects output from the specified executor, aggregates results, and exposes the aggregated
    /// output.</returns>
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
