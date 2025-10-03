// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

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
    private readonly record struct EdgeConnection(string SourceId, string TargetId)
    {
        public override string ToString() => $"{this.SourceId} -> {this.TargetId}";
    }

    private int _edgeCount;
    private readonly Dictionary<string, ExecutorRegistration> _executors = [];
    private readonly Dictionary<string, HashSet<Edge>> _edges = [];
    private readonly HashSet<string> _unboundExecutors = [];
    private readonly HashSet<EdgeConnection> _conditionlessConnections = [];
    private readonly Dictionary<string, RequestPort> _inputPorts = [];
    private readonly HashSet<string> _outputExecutors = [];

    private readonly string _startExecutorId;

    private static readonly string s_namespace = typeof(WorkflowBuilder).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

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
        // If the executor is unbound, create an entry for it, unless it already exists.
        // Otherwise, update the entry for it, and remove the unbound tag
        if (executorish.IsUnbound && !this._executors.ContainsKey(executorish.Id))
        {
            // If this is an unbound executor, we need to track it separately
            this._unboundExecutors.Add(executorish.Id);
        }
        else if (!executorish.IsUnbound)
        {
            ExecutorRegistration incoming = executorish.Registration;
            // If there is already a bound executor with this ID, we need to validate (to best efforts)
            // that the two are matching (at least based on type)
            if (this._executors.TryGetValue(executorish.Id, out ExecutorRegistration? existing))
            {
                if (existing.ExecutorType != incoming.ExecutorType)
                {
                    throw new InvalidOperationException(
                        $"Cannot bind executor with ID '{executorish.Id}' because an executor with the same ID but a different type ({existing.ExecutorType.Name} vs {incoming.ExecutorType.Name}) is already bound.");
                }

                if (existing.RawExecutorishData is not null &&
                    !ReferenceEquals(existing.RawExecutorishData, incoming.RawExecutorishData))
                {
                    throw new InvalidOperationException(
                        $"Cannot bind executor with ID '{executorish.Id}' because an executor with the same ID but different instance is already bound.");
                }
            }
            else
            {
                this._executors[executorish.Id] = executorish.Registration;
                if (this._unboundExecutors.Contains(executorish.Id))
                {
                    this._unboundExecutors.Remove(executorish.Id);
                }
            }
        }

        if (executorish.ExecutorType == ExecutorIsh.Type.RequestPort)
        {
            RequestPort port = executorish._requestPortValue!;
            this._inputPorts[port.Id] = port;
        }

        return executorish;
    }

    /// <summary>
    /// Register executors as an output source. Executors can use <see cref="IWorkflowContext.YieldOutputAsync"/> to yield output values.
    /// By default, message handlers with a non-void return type will also be yielded, unless <see cref="ExecutorOptions.AutoYieldOutputHandlerResultObject"/>
    /// is set to <see langword="false"/>.
    /// </summary>
    /// <param name="executors"></param>
    /// <returns></returns>
    public WorkflowBuilder WithOutputFrom(params ExecutorIsh[] executors)
    {
        foreach (ExecutorIsh executor in executors)
        {
            this._outputExecutors.Add(this.Track(executor).Id);
        }

        return this;
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

        this._executors[executor.Id] = new ExecutorIsh(executor).Registration;
        this._unboundExecutors.Remove(executor.Id);
        return this;
    }

    private HashSet<Edge> EnsureEdgesFor(string sourceId)
    {
        // Ensure that there is a set of edges for the given source ID.
        // If it does not exist, create a new one.
        if (!this._edges.TryGetValue(sourceId, out HashSet<Edge>? edges))
        {
            this._edges[sourceId] = edges = [];
        }

        return edges;
    }

    /// <summary>
    /// Adds a directed edge from the specified source executor to the target executor, optionally guarded by a
    /// condition.
    /// </summary>
    /// <param name="source">The executor that acts as the source node of the edge. Cannot be null.</param>
    /// <param name="target">The executor that acts as the target node of the edge. Cannot be null.</param>
    /// <param name="idempotent">If set to <see langword="true"/>, adding the same edge multiple times will be a NoOp,
    /// rather than an error.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if an unconditional edge between the specified source and target
    /// executors already exists.</exception>
    public WorkflowBuilder AddEdge(ExecutorIsh source, ExecutorIsh target, bool idempotent = false)
        => this.AddEdge<object>(source, target, null, idempotent);

    internal static Func<object?, bool>? CreateConditionFunc<T>(Func<T?, bool>? condition)
    {
        if (condition is null)
        {
            return null;
        }
        return maybeObj =>
        {
            if (typeof(T) != typeof(object) && maybeObj is PortableValue portableValue)
            {
                maybeObj = portableValue.AsType(typeof(T));
            }
            return condition(maybeObj is T typed ? typed : default);
        };
    }

    internal static Func<object?, bool>? CreateConditionFunc<T>(Func<object?, bool>? condition)
    {
        if (condition is null)
        {
            return null;
        }
        return maybeObj =>
        {
            if (typeof(T) != typeof(object) && maybeObj is PortableValue portableValue)
            {
                maybeObj = portableValue.AsType(typeof(T));
            }

            if (maybeObj is T typed)
            {
                return condition(typed);
            }

            return condition(null);
        };
    }

    private EdgeId TakeEdgeId() => new(Interlocked.Increment(ref this._edgeCount));

    /// <summary>
    /// Adds a directed edge from the specified source executor to the target executor, optionally guarded by a
    /// condition.
    /// </summary>
    /// <param name="source">The executor that acts as the source node of the edge. Cannot be null.</param>
    /// <param name="target">The executor that acts as the target node of the edge. Cannot be null.</param>
    /// <param name="condition">An optional predicate that determines whether the edge should be followed based on the input.
    /// <param name="idempotent">If set to <see langword="true"/>, adding the same edge multiple times will be a NoOp,
    /// rather than an error.</param>
    /// If null, the edge is always activated when the source sends a message.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if an unconditional edge between the specified source and target
    /// executors already exists.</exception>
    public WorkflowBuilder AddEdge<T>(ExecutorIsh source, ExecutorIsh target, Func<T?, bool>? condition = null, bool idempotent = false)
    {
        // Add an edge from source to target with an optional condition.
        // This is a low-level builder method that does not enforce any specific executor type.
        // The condition can be used to determine if the edge should be followed based on the input.
        Throw.IfNull(source);
        Throw.IfNull(target);

        EdgeConnection connection = new(source.Id, target.Id);
        if (condition is null && this._conditionlessConnections.Contains(connection))
        {
            if (idempotent)
            {
                return this;
            }

            throw new InvalidOperationException(
                $"An edge from '{source.Id}' to '{target.Id}' already exists without a condition. " +
                "You cannot add another edge without a condition for the same source and target.");
        }

        DirectEdgeData directEdge = new(this.Track(source).Id, this.Track(target).Id, this.TakeEdgeId(), CreateConditionFunc(condition));

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
    /// <param name="targets">One or more target executors that will receive the fan-out edge. Cannot be null or empty.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    public WorkflowBuilder AddFanOutEdge(ExecutorIsh source, params IEnumerable<ExecutorIsh> targets)
        => this.AddFanOutEdge<object>(source, null, targets);

    internal static Func<object?, int, IEnumerable<int>>? CreateEdgeAssignerFunc<T>(Func<T?, int, IEnumerable<int>>? partitioner)
    {
        if (partitioner is null)
        {
            return null;
        }

        return (maybeObj, count) =>
        {
            if (typeof(T) != typeof(object) && maybeObj is PortableValue portableValue)
            {
                maybeObj = portableValue.AsType(typeof(T));
            }

            return partitioner(maybeObj is T typed ? typed : default, count);
        };
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
    public WorkflowBuilder AddFanOutEdge<T>(ExecutorIsh source, Func<T?, int, IEnumerable<int>>? partitioner = null, params IEnumerable<ExecutorIsh> targets)
    {
        Throw.IfNull(source);
        Throw.IfNull(targets);

        List<string> sinkIds = targets.Select(target =>
        {
            Throw.IfNull(target, nameof(targets));
            return this.Track(target).Id;
        }).ToList();

        Throw.IfNullOrEmpty(sinkIds, nameof(targets));

        FanOutEdgeData fanOutEdge = new(
            this.Track(source).Id,
            sinkIds,
            this.TakeEdgeId(),
            CreateEdgeAssignerFunc(partitioner));

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
    public WorkflowBuilder AddFanInEdge(ExecutorIsh target, params IEnumerable<ExecutorIsh> sources)
    {
        Throw.IfNull(target);
        Throw.IfNull(sources);

        List<string> sourceIds = sources.Select(source =>
        {
            Throw.IfNull(source, nameof(sources));
            return this.Track(source).Id;
        }).ToList();

        Throw.IfNullOrEmpty(sourceIds, nameof(sources));

        FanInEdgeData edgeData = new(
            sourceIds,
            this.Track(target).Id,
            this.TakeEdgeId());

        foreach (string sourceId in edgeData.SourceIds)
        {
            this.EnsureEdgesFor(sourceId).Add(new(edgeData));
        }

        return this;
    }

    private void Validate()
    {
        if (this._unboundExecutors.Count > 0)
        {
            throw new InvalidOperationException(
                $"Workflow cannot be built because there are unbound executors: {string.Join(", ", this._unboundExecutors)}.");
        }

        // TODO: This is likely a pipe-dream, but can we do any type-checking on the edges? (Not without instantiating the executors...)
    }

    private Workflow BuildInternal(Activity? activity = null)
    {
        activity?.AddEvent(new ActivityEvent(EventNames.BuildStarted));

        try
        {
            this.Validate();
        }
        catch (Exception ex) when (activity is not null)
        {
            activity.AddEvent(new ActivityEvent(EventNames.BuildError, tags: new() {
                { Tags.BuildErrorMessage, ex.Message },
                { Tags.BuildErrorType, ex.GetType().FullName }
            }));
            activity.CaptureException(ex);
            throw;
        }

        activity?.AddEvent(new ActivityEvent(EventNames.BuildValidationCompleted));

        var workflow = new Workflow(this._startExecutorId)
        {
            Registrations = this._executors,
            Edges = this._edges,
            Ports = this._inputPorts,
            OutputExecutors = this._outputExecutors
        };

        // Using the start executor ID as a proxy for the workflow ID
        activity?.SetTag(Tags.WorkflowId, workflow.StartExecutorId);
        if (activity is not null)
        {
            var workflowJsonDefinitionData = new WorkflowJsonDefinitionData
            {
                StartExecutorId = this._startExecutorId,
                Edges = this._edges.Values.SelectMany(e => e),
                Ports = this._inputPorts.Values,
                OutputExecutors = this._outputExecutors
            };
            activity.SetTag(
                Tags.WorkflowDefinition,
                JsonSerializer.Serialize(
                    workflowJsonDefinitionData,
                    WorkflowJsonDefinitionJsonContext.Default.WorkflowJsonDefinitionData
                )
            );
        }

        return workflow;
    }

    /// <summary>
    /// Builds and returns a workflow instance.
    /// </summary>
    /// <exception cref="InvalidOperationException">Thrown if there are unbound executors in the workflow definition,
    /// or if the start executor is not bound.</exception>
    public Workflow Build()
    {
        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowBuild);

        var workflow = this.BuildInternal(activity);

        activity?.AddEvent(new ActivityEvent(EventNames.BuildCompleted));

        return workflow;
    }

    /// <summary>
    /// Attempts to build a workflow instance configured to process messages of the specified input type.
    /// </summary>
    /// <typeparam name="TInput">The desired input type for the workflow.</typeparam>
    /// <exception cref="InvalidOperationException">Thrown if the built workflow cannot process messages of the specified input type,</exception>
    public async ValueTask<Workflow<TInput>> BuildAsync<TInput>() where TInput : notnull
    {
        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowBuild);

        Workflow<TInput>? maybeWorkflow = await this.BuildInternal(activity)
                                                    .TryPromoteAsync<TInput>()
                                                    .ConfigureAwait(false);

        if (maybeWorkflow is null)
        {
            var exception = new InvalidOperationException(
                $"The built workflow cannot process input of type '{typeof(TInput).FullName}'.");
            activity?.AddEvent(new ActivityEvent(EventNames.BuildError, tags: new() {
                { Tags.BuildErrorMessage, exception.Message },
                { Tags.BuildErrorType, exception.GetType().FullName }
            }));
            activity?.CaptureException(exception);
            throw exception;
        }

        activity?.AddEvent(new ActivityEvent(EventNames.BuildCompleted));

        return maybeWorkflow;
    }
}
