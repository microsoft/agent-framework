// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A factory method that produces an executor instance.
/// </summary>
/// <typeparam name="TExecutor">The executor type.</typeparam>
/// <returns>A new <typeparamref name="TExecutor"/> instance.</returns>
public delegate TExecutor ExecutorProvider<out TExecutor>()
    where TExecutor : Executor;

/// <summary>
/// Provides a builder for constructing and configuring a workflow by defining executors and the connections between
/// them.
/// </summary>
/// <remarks>Use the WorkflowBuilder to incrementally add executors and edges, including fan-in and fan-out
/// patterns, before building a strongly-typed workflow instance. Executors must be bound before building the workflow.
/// All executors must be bound by calling into <see cref="BindExecutor"/> if they were intially specified as
/// <see cref="ExecutorIsh.Type.Unbound"/>.</remarks>
public class WorkflowBuilder
{
    private record struct EdgeId(string SourceId, string TargetId)
    {
        public override string ToString() => $"{this.SourceId} -> {this.TargetId}";
    }

    private readonly Dictionary<string, ExecutorProvider<Executor>> _executors = new();
    private readonly Dictionary<string, HashSet<Edge>> _edges = new();
    private readonly HashSet<string> _unboundExecutors = new();
    private readonly HashSet<EdgeId> _conditionlessEdges = new();
    private readonly Dictionary<string, InputPort> _inputPorts = new();

    private readonly string _startExecutorId;

    /// <summary>
    /// Initializes a new instance of the WorkflowBuilder class with the specified starting executor.
    /// </summary>
    /// <param name="start">The executor that defines the starting point of the workflow. Cannot be null.</param>
    public WorkflowBuilder(ExecutorIsh start)
    {
        this._startExecutorId = this.Track(start).Id;
    }

    private ExecutorIsh Track(ExecutorIsh executorish)
    {
        ExecutorProvider<Executor> provider = executorish.ExecutorProvider;

        // If the executor is unbound, create an entry for it, unless it already exists.
        // Otherwise, update the entry for it, and remove the unbound tag
        if (executorish.IsUnbound && !this._executors.ContainsKey(executorish.Id))
        {
            // If this is an unbound executor, we need to track it separately
            this._unboundExecutors.Add(executorish.Id);
            this._executors[executorish.Id] = provider;
        }
        else if (!executorish.IsUnbound)
        {
            // If we already have an executor with this ID, we need to update it (todo: should we throw on double binding?)
            this._executors[executorish.Id] = provider;
        }

        if (executorish.ExecutorType == ExecutorIsh.Type.InputPort)
        {
            InputPort port = executorish._inputPortValue!;
            this._inputPorts[port.Id] = port;
        }

        return executorish;
    }

    private void UpdateExecutor(string id, ExecutorProvider<Executor> provider)
    {
        this._executors[id] = provider;
    }

    /// <summary>
    /// Binds the specified executor to the workflow, allowing it to participate in workflow execution.
    /// </summary>
    /// <param name="executor">The executor instance to bind. The executor must exist in the workflow and not be already bound.</param>
    /// <returns>The current <see cref="WorkflowBuilder"/> instance, enabling fluent configuration.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the specified executor is already bound or does not exist in the workflow.</exception>
    public WorkflowBuilder BindExecutor(Executor executor)
    {
        if (!this._unboundExecutors.Contains(executor.Id))
        {
            throw new InvalidOperationException(
                $"Executor with ID '{executor.Id}' is already bound or does not exist in the workflow.");
        }

        this._executors[executor.Id] = () => executor;
        this._unboundExecutors.Remove(executor.Id);
        return this;
    }

    private HashSet<Edge> EnsureEdgesFor(string sourceId)
    {
        // Ensure that there is a set of edges for the given source ID.
        // If it does not exist, create a new one.
        if (!this._edges.TryGetValue(sourceId, out HashSet<Edge>? edges))
        {
            this._edges[sourceId] = edges = new HashSet<Edge>();
        }

        return edges;
    }

    /// <summary>
    /// Adds a directed edge from the specified source executor to the target executor, optionally guarded by a
    /// condition.
    /// </summary>
    /// <param name="source">The executor that acts as the source node of the edge. Cannot be null.</param>
    /// <param name="target">The executor that acts as the target node of the edge. Cannot be null.</param>
    /// <param name="condition">An optional predicate that determines whether the edge should be followed based on the input.
    /// If null, the edge is always activated when the source sends a message.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if an unconditional edge between the specified source and target
    /// executors already exists.</exception>
    public WorkflowBuilder AddEdge(ExecutorIsh source, ExecutorIsh target, Func<object?, bool>? condition = null)
    {
        // Add an edge from source to target with an optional condition.
        // This is a low-level builder method that does not enforce any specific executor type.
        // The condition can be used to determine if the edge should be followed based on the input.
        Throw.IfNull(source);
        Throw.IfNull(target);

        EdgeId id = new(source.Id, target.Id);
        if (condition == null && this._conditionlessEdges.Contains(id))
        {
            throw new InvalidOperationException(
                $"An edge from '{source.Id}' to '{target.Id}' already exists without a condition. " +
                "You cannot add another edge without a condition for the same source and target.");
        }

        DirectEdgeData directEdge = new(this.Track(source).Id, this.Track(target).Id, condition);

        this.EnsureEdgesFor(source.Id).Add(new(directEdge));

        return this;
    }

    /// <summary>
    /// Adds a fan-out edge from the specified source executor to one or more target executors, optionally using a
    /// custom partitioning function.
    /// </summary>
    /// <remarks>If a partitioner function is provided, it will be used to distribute input across the target
    /// executors. The order of targets determines their mapping in the partitioning process.</remarks>
    /// <param name="source">The source executor from which the fan-out edge originates. Cannot be null.</param>
    /// <param name="partitioner">An optional function that determines how input is partitioned among the target executors.
    /// If null, messages will route to all targets.</param>
    /// <param name="targets">One or more target executors that will receive the fan-out edge. Cannot be null or empty.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    public WorkflowBuilder AddFanOutEdge(ExecutorIsh source, Func<object?, int, IEnumerable<int>>? partitioner = null, params ExecutorIsh[] targets)
    {
        Throw.IfNull(source);
        Throw.IfNullOrEmpty(targets);

        FanOutEdgeData fanOutEdge = new(
                this.Track(source).Id,
                targets.Select(target => this.Track(target).Id).ToList(),
                partitioner);

        this.EnsureEdgesFor(source.Id).Add(new(fanOutEdge));

        return this;
    }

    /// <summary>
    /// Adds a fan-in edge to the workflow, connecting multiple source executors to a single target executor with an
    /// optional trigger condition.
    /// </summary>
    /// <remarks>This method establishes a fan-in relationship, allowing the target executor to be activated
    /// based on the completion or state of multiple sources. The trigger parameter can be used to customize activation
    /// behavior.</remarks>
    /// <param name="target">The target executor that receives input from the specified source executors. Cannot be null.</param>
    /// <param name="sources">One or more source executors that provide input to the target. Cannot be null or empty.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    public WorkflowBuilder AddFanInEdge(ExecutorIsh target, params ExecutorIsh[] sources)
    {
        Throw.IfNull(target);
        Throw.IfNullOrEmpty(sources);

        FanInEdgeData edgeData = new(
            sources.Select(source => this.Track(source).Id).ToList(),
                this.Track(target).Id);

        foreach (string sourceId in edgeData.SourceIds)
        {
            this.EnsureEdgesFor(sourceId).Add(new(edgeData));
        }

        return this;
    }

    /// <summary>
    /// Builds and returns a workflow instance configured to process messages of the specified input type.
    /// </summary>
    /// <typeparam name="T">The type of input messages that the workflow will accept and process.</typeparam>
    /// <returns>A new instance of <see cref="Workflow{T}"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if there are unbound executors in the workflow definition,
    /// if the start executor is not bound, or if the start executor does not contain a handler for the specified input
    /// type <typeparamref name="T"/>.</exception>
    public Workflow<T> Build<T>()
    {
        if (this._unboundExecutors.Count > 0)
        {
            throw new InvalidOperationException(
                $"Workflow cannot be built because there are unbound executors: {string.Join(", ", this._unboundExecutors)}.");
        }

        // Grab the start node, and make sure it has the right type?
        if (!this._executors.TryGetValue(this._startExecutorId, out ExecutorProvider<Executor>? startProvider))
        {
            // TODO: This should never be able to be hit
            throw new InvalidOperationException($"Start executor with ID '{this._startExecutorId}' is not bound.");
        }

        // TODO: Delay-instantiate the start executor, and ensure it is of type T.
        Executor startExecutor = startProvider();

        if (!startExecutor.InputTypes.Any(t => t.IsAssignableFrom(typeof(T))))
        {
            // We have no handlers for the input type T, which means the built workflow will not be able to
            // process messages of the desired type
            throw new InvalidOperationException(
                $"Workflow cannot be built because the starting executor {this._startExecutorId} does not contain a handler for the desired input type {typeof(T).Name}");
        }

        return new Workflow<T>(this._startExecutorId) // Why does it not see the default ctor?
        {
            ExecutorProviders = this._executors,
            Edges = this._edges,
            Ports = this._inputPorts
        };
    }
}
