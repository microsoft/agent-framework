// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for configuring and building workflows using the WorkflowBuilder type.
/// </summary>
/// <remarks>These extension methods simplify the process of connecting executors, adding external calls, and
/// constructing workflows with output aggregation. They are intended to streamline workflow graph construction and
/// promote common patterns for chaining and aggregating workflow steps.</remarks>
public static class WorkflowBuilderExtensions
{
    /// <summary>
    /// Adds edges to the workflow that forward messages of the specified type from the source executor to
    /// one or more target executors.
    /// </summary>
    /// <typeparam name="TMessage">The type of message to forward.</typeparam>
    /// <param name="builder">The <see cref="WorkflowBuilder"/> to which the edges will be added.</param>
    /// <param name="source">The source executor from which messages will be forwarded.</param>
    /// <param name="executors">The target executors to which messages will be forwarded.</param>
    /// <returns>The updated <see cref="WorkflowBuilder"/> instance.</returns>
    public static WorkflowBuilder ForwardMessage<TMessage>(this WorkflowBuilder builder, ExecutorIsh source, params IEnumerable<ExecutorIsh> executors)
        => builder.ForwardMessage<TMessage>(source, condition: null, executors);

    /// <summary>
    /// Adds edges to the workflow that forward messages of the specified type from the source executor to
    /// one or more target executors.
    /// </summary>
    /// <typeparam name="TMessage">The type of message to forward.</typeparam>
    /// <param name="builder">The <see cref="WorkflowBuilder"/> to which the edges will be added.</param>
    /// <param name="source">The source executor from which messages will be forwarded.</param>
    /// <param name="condition">An optional condition that messages must satisfy to be forwarded. If <see langword="null"/>,
    /// all messages of type <typeparamref name="TMessage"/> will be forwarded.</param>
    /// <param name="executors">The target executors to which messages will be forwarded.</param>
    /// <returns>The updated <see cref="WorkflowBuilder"/> instance.</returns>
    public static WorkflowBuilder ForwardMessage<TMessage>(this WorkflowBuilder builder, ExecutorIsh source, Func<TMessage, bool>? condition = null, params IEnumerable<ExecutorIsh> executors)
    {
        Throw.IfNull(executors);

        Func<object?, bool> predicate = WorkflowBuilder.CreateConditionFunc<TMessage>(IsAllowedTypeAndMatchingCondition)!;

#if NET
        if (executors.TryGetNonEnumeratedCount(out int count) && count == 1)
#else
        if (executors is ICollection<ExecutorIsh> { Count: 1 })
#endif
        {
            return builder.AddEdge(source, executors.First(), predicate);
        }

        return builder.AddSwitch(source, (switch_) => switch_.AddCase(predicate, executors));

        // The reason we can check for "not null" here is that CreateConditionFunc<T> will do the correct unwrapping
        // logic for PortableValues.
        bool IsAllowedTypeAndMatchingCondition(TMessage? message) => message != null && (condition == null || condition(message));
    }

    /// <summary>
    /// Adds edges from the specified source to the provided executors, excluding messages of a specified type.
    /// </summary>
    /// <typeparam name="TMessage">The type of messages to exclude from being forwarded to the executors.</typeparam>
    /// <param name="builder">The <see cref="WorkflowBuilder"/> instance to which the edges will be added.</param>
    /// <param name="source">The source executor from which messages will be forwarded.</param>
    /// <param name="executors">The target executors to which messages, except those of type <typeparamref name="TMessage"/>, will be forwarded.</param>
    /// <returns>The updated <see cref="WorkflowBuilder"/> instance with the added edges.</returns>
    public static WorkflowBuilder ForwardExcept<TMessage>(this WorkflowBuilder builder, ExecutorIsh source, params IEnumerable<ExecutorIsh> executors)
    {
        Throw.IfNull(executors);

        Func<object?, bool> predicate = WorkflowBuilder.CreateConditionFunc<TMessage>((Func<object?, bool>)IsAllowedType)!;

#if NET
        if (executors.TryGetNonEnumeratedCount(out int count) && count == 1)
#else
        if (executors is ICollection<ExecutorIsh> { Count: 1 })
#endif
        {
            return builder.AddEdge(source, executors.First(), predicate);
        }

        return builder.AddSwitch(source, (switch_) => switch_.AddCase(predicate, executors));

        // The reason we can check for "null" here is that CreateConditionFunc<T> will do the correct unwrapping
        // logic for PortableValues.
        static bool IsAllowedType(object? message) => message is null;
    }

    /// <summary>
    /// Adds a sequential chain of executors to the workflow, connecting each executor in order so that each is
    /// executed after the previous one.
    /// </summary>
    /// <remarks>Each executor in the chain is connected so that execution flows from the source to each subsequent
    /// executor in the order provided.</remarks>
    /// <param name="builder">The workflow builder to which the executor chain will be added. </param>
    /// <param name="source">The initial executor in the chain. Cannot be null.</param>
    /// <param name="allowRepetition">If set to <see langword="true"/>, the same executor can be added to the chain multiple times.</param>
    /// <param name="executors">An ordered array of executors to be added to the chain after the source.</param>
    /// <returns>The original workflow builder instance with the specified executor chain added.</returns>
    /// <exception cref="ArgumentException">Thrown if there is a cycle in the chain.</exception>
    public static WorkflowBuilder AddChain(this WorkflowBuilder builder, ExecutorIsh source, bool allowRepetition = false, params IEnumerable<ExecutorIsh> executors)
    {
        Throw.IfNull(builder);
        Throw.IfNull(source);

        HashSet<string> seenExecutors = [source.Id];

        foreach (var executor in executors)
        {
            Throw.IfNull(executor, nameof(executors));

            if (!allowRepetition && seenExecutors.Contains(executor.Id))
            {
                throw new ArgumentException($"Executor '{executor.Id}' is already in the chain.", nameof(executors));
            }
            seenExecutors.Add(executor.Id);

            builder.AddEdge(source, executor, idempotent: true);
            source = executor;
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

        RequestPort port = new(portId, typeof(TRequest), typeof(TResponse));
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
}
