// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;
using System.Collections.Concurrent;

#pragma warning restore IDE0005 // Using directive is unnecessary.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A factory method that produces an executor instance.
/// </summary>
/// <typeparam name="TExecutor">The executor type.</typeparam>
/// <returns>A new <typeparamref name="TExecutor"/> instance.</returns>
public delegate TExecutor ExecutorProvider<out TExecutor>()
    where TExecutor : Executor;

/// <summary>
/// .
/// </summary>
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

    private readonly string _startExecutorId;

    /// <summary>
    /// .
    /// </summary>
    /// <param name="start"></param>
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

        return executorish;
    }

    private void UpdateExecutor(string id, ExecutorProvider<Executor> provider)
    {
        this._executors[id] = provider;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="executor"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
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
    /// .
    /// </summary>
    /// <param name="source"></param>
    /// <param name="target"></param>
    /// <param name="condition"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
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

        this.EnsureEdgesFor(source.Id)
            .Add(new DirectEdgeData(this.Track(source).Id, this.Track(target).Id, condition));

        return this;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="source"></param>
    /// <param name="partitioner"></param>
    /// <param name="targets"></param>
    /// <returns></returns>
    public WorkflowBuilder AddFanOutEdge(ExecutorIsh source, Func<object?, int, IEnumerable<int>>? partitioner = null, params ExecutorIsh[] targets)
    {
        Throw.IfNull(source);
        Throw.IfNullOrEmpty(targets);

        this.EnsureEdgesFor(source.Id)
            .Add(new FanOutEdgeData(
                this.Track(source).Id,
                targets.Select(target => this.Track(target).Id).ToList(),
                partitioner));

        return this;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="target"></param>
    /// <param name="trigger"></param>
    /// <param name="sources"></param>
    /// <returns></returns>
    public WorkflowBuilder AddFanInEdge(ExecutorIsh target, FanInTrigger trigger = default, params ExecutorIsh[] sources)
    {
        Throw.IfNull(target);
        Throw.IfNullOrEmpty(sources);

        FanInEdgeData edgeData = new(
            sources.Select(source => this.Track(source).Id).ToList(),
                this.Track(target).Id,
                trigger);

        foreach (string sourceId in edgeData.SourceIds)
        {
            this.EnsureEdgesFor(sourceId).Add(edgeData);
        }

        return this;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="T"></typeparam>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
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
            Edges = this._edges
        };
    }
}
