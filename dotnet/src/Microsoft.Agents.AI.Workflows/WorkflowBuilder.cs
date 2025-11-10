// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Microsoft.Agents.AI.Workflows.Checkpointing;
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
/// <see cref="ExecutorBinding.IsPlaceholder"/>.</remarks>
public class WorkflowBuilder
{
    private readonly record struct EdgeConnection(string SourceId, string TargetId)
    {
        public override string ToString() => $"{this.SourceId} -> {this.TargetId}";
    }

    private int _edgeCount;
    private readonly Dictionary<string, ExecutorBinding> _executorBindings = [];
    private readonly Dictionary<string, HashSet<Edge>> _edges = [];
    private readonly HashSet<string> _unboundExecutors = [];
    private readonly HashSet<EdgeConnection> _conditionlessConnections = [];
    private readonly Dictionary<string, RequestPort> _requestPorts = [];
    private readonly HashSet<string> _outputExecutors = [];

    private readonly string _startExecutorId;
    private string? _name;
    private string? _description;

    private static readonly string s_namespace = typeof(WorkflowBuilder).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

    /// <summary>
    /// Initializes a new instance of the WorkflowBuilder class with the specified starting executor.
    /// </summary>
    /// <param name="start">The executor that defines the starting point of the workflow. Cannot be null.</param>
    public WorkflowBuilder(ExecutorBinding start)
    {
        this._startExecutorId = this.Track(start).Id;
    }

    private ExecutorBinding Track(ExecutorBinding binding)
    {
        // If the executor is unbound, create an entry for it, unless it already exists.
        // Otherwise, update the entry for it, and remove the unbound tag
        if (binding.IsPlaceholder && !this._executorBindings.ContainsKey(binding.Id))
        {
            // If this is an unbound executor, we need to track it separately
            this._unboundExecutors.Add(binding.Id);
        }
        else if (!binding.IsPlaceholder)
        {
            // If there is already a bound executor with this ID, we need to validate (to best efforts)
            // that the two are matching (at least based on type)
            if (this._executorBindings.TryGetValue(binding.Id, out ExecutorBinding? existing))
            {
                if (existing.ExecutorType != binding.ExecutorType)
                {
                    throw new InvalidOperationException(
                        $"Cannot bind executor with ID '{binding.Id}' because an executor with the same ID but a different type ({existing.ExecutorType.Name} vs {binding.ExecutorType.Name}) is already bound.");
                }

                if (existing.RawValue is not null &&
                    !ReferenceEquals(existing.RawValue, binding.RawValue))
                {
                    throw new InvalidOperationException(
                        $"Cannot bind executor with ID '{binding.Id}' because an executor with the same ID but different instance is already bound.");
                }
            }
            else
            {
                this._executorBindings[binding.Id] = binding;
                if (this._unboundExecutors.Contains(binding.Id))
                {
                    this._unboundExecutors.Remove(binding.Id);
                }
            }
        }

        if (binding is RequestPortBinding portRegistration)
        {
            RequestPort port = portRegistration.Port;
            this._requestPorts[port.Id] = port;
        }

        return binding;
    }

    /// <summary>
    /// Register executors as an output source. Executors can use <see cref="IWorkflowContext.YieldOutputAsync"/> to yield output values.
    /// By default, message handlers with a non-void return type will also be yielded, unless <see cref="ExecutorOptions.AutoYieldOutputHandlerResultObject"/>
    /// is set to <see langword="false"/>.
    /// </summary>
    /// <param name="executors"></param>
    /// <returns></returns>
    public WorkflowBuilder WithOutputFrom(params ExecutorBinding[] executors)
    {
        foreach (ExecutorBinding executor in executors)
        {
            this._outputExecutors.Add(this.Track(executor).Id);
        }

        return this;
    }

    /// <summary>
    /// Sets the human-readable name for the workflow.
    /// </summary>
    /// <param name="name">The name of the workflow.</param>
    /// <returns>The current <see cref="WorkflowBuilder"/> instance, enabling fluent configuration.</returns>
    public WorkflowBuilder WithName(string name)
    {
        this._name = name;
        return this;
    }

    /// <summary>
    /// Sets the description for the workflow.
    /// </summary>
    /// <param name="description">The description of what the workflow does.</param>
    /// <returns>The current <see cref="WorkflowBuilder"/> instance, enabling fluent configuration.</returns>
    public WorkflowBuilder WithDescription(string description)
    {
        this._description = description;
        return this;
    }

    /// <summary>
    /// Binds the specified executor (via registration) to the workflow, allowing it to participate in workflow execution.
    /// </summary>
    /// <param name="registration">The executor instance to bind. The executor must exist in the workflow and not be already bound.</param>
    /// <returns>The current <see cref="WorkflowBuilder"/> instance, enabling fluent configuration.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the specified executor is already bound or does not exist in the workflow.</exception>
    public WorkflowBuilder BindExecutor(ExecutorBinding registration)
    {
        if (Throw.IfNull(registration) is ExecutorPlaceholder)
        {
            throw new InvalidOperationException(
                $"Cannot bind executor with ID '{registration.Id}' because it is a placeholder registration. " +
                "You must provide a concrete executor instance or registration.");
        }

        this.Track(registration);
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
    public WorkflowBuilder AddEdge(ExecutorBinding source, ExecutorBinding target, bool idempotent = false)
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
    public WorkflowBuilder AddEdge<T>(ExecutorBinding source, ExecutorBinding target, Func<T?, bool>? condition = null, bool idempotent = false)
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
    public WorkflowBuilder AddFanOutEdge(ExecutorBinding source, IEnumerable<ExecutorBinding> targets)
        => this.AddFanOutEdge<object>(source, targets, null);

    internal static Func<object?, int, IEnumerable<int>>? CreateTargetAssignerFunc<T>(Func<T?, int, IEnumerable<int>>? targetAssigner)
    {
        if (targetAssigner is null)
        {
            return null;
        }

        return (maybeObj, count) =>
        {
            if (typeof(T) != typeof(object) && maybeObj is PortableValue portableValue)
            {
                maybeObj = portableValue.AsType(typeof(T));
            }

            return targetAssigner(maybeObj is T typed ? typed : default, count);
        };
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
    /// <param name="targetSelector">An optional function that determines how input is assigned among the target executors.
    /// If null, messages will route to all targets.</param>
    public WorkflowBuilder AddFanOutEdge<T>(ExecutorBinding source, IEnumerable<ExecutorBinding> targets, Func<T?, int, IEnumerable<int>>? targetSelector = null)
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
            CreateTargetAssignerFunc(targetSelector));

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
    /// <param name="sources">One or more source executors that provide input to the target. Cannot be null or empty.</param>
    /// <param name="target">The target executor that receives input from the specified source executors. Cannot be null.</param>
    /// <returns>The current instance of <see cref="WorkflowBuilder"/>.</returns>
    public WorkflowBuilder AddFanInEdge(IEnumerable<ExecutorBinding> sources, ExecutorBinding target)
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

    /// <inheritdoc cref="AddFanInEdge(IEnumerable{ExecutorBinding}, ExecutorBinding)"/>
    [Obsolete("Use AddFanInEdge(IEnumerable<ExecutorBinding>, ExecutorBinding) instead.")]
    public WorkflowBuilder AddFanInEdge(ExecutorBinding target, params IEnumerable<ExecutorBinding> sources)
        => this.AddFanInEdge(sources, target);

    private void Validate(bool validateOrphans)
    {
        // Check that there are no "unbound" (defined as placeholders that have not been replaced by real bindings)
        // executors.
        if (this._unboundExecutors.Count > 0)
        {
            throw new InvalidOperationException(
                $"Workflow cannot be built because there are unbound executors: {string.Join(", ", this._unboundExecutors)}.");
        }

        // Make sure that all nodes are connected to the start executor (transitively)
        HashSet<string> remainingExecutors = new(this._executorBindings.Keys);
        Queue<string> toVisit = new([this._startExecutorId]);

        if (!validateOrphans)
        {
            return;
        }

        while (toVisit.Count > 0)
        {
            string currentId = toVisit.Dequeue();
            bool unvisited = remainingExecutors.Remove(currentId);

            if (unvisited &&
                this._edges.TryGetValue(currentId, out HashSet<Edge>? outgoingEdges))
            {
                foreach (Edge edge in outgoingEdges)
                {
                    switch (edge.Data)
                    {
                        case DirectEdgeData directEdgeData:
                            toVisit.Enqueue(directEdgeData.SinkId);
                            break;
                        case FanOutEdgeData fanOutEdgeData:
                            foreach (string targetId in fanOutEdgeData.SinkIds)
                            {
                                toVisit.Enqueue(targetId);
                            }
                            break;
                        case FanInEdgeData fanInEdgeData:
                            toVisit.Enqueue(fanInEdgeData.SinkId);
                            break;
                    }

                    // Ideally we would be able to validate that the types accepted by the target executor(s) are compatible
                    // with those produced by the source executor. However, this is not possible at this time for a number of
                    // reasons:
                    //
                    // - Right now we do not require users to specify the types produced by Executors exhaustively. This will
                    //   likely change at some point in the future as part of implementing support for polymorphism in message
                    //   handling. Until then it cannot be clear what types are produced by an upstream Executor.
                    // - Edges with conditionals / target selectors can route messages
                    // - We intend to expand the API surface of FanIn edges to allow different aggregation and synchronization
                    //   strategies; this could introduce type transformations which we may not be able to validate here.
                    // - All of the above seem like they can be solved with some effort, but the biggest blocker is that we
                    //   currently support async Executor factories, and Executors register message handlers at runtime, so we
                    //   cannot know which types they accept until they are instantiated, and we cannot instantiate them at
                    //   build time because we are in an obligate (for DI-compatibility) synchronous context.
                    //
                    // TODO: Revisit the async Executor factory decision if we have a way to deal with "conditional" and
                    //   "target selector-based" routing.
                }
            }
        }

        if (remainingExecutors.Count > 0)
        {
            throw new InvalidOperationException(
                $"Workflow cannot be built because there are unreachable executors: {string.Join(", ", remainingExecutors)}.");
        }
    }

    private Workflow BuildInternal(bool validateOrphans, Activity? activity = null)
    {
        activity?.AddEvent(new ActivityEvent(EventNames.BuildStarted));

        try
        {
            this.Validate(validateOrphans);
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

        var workflow = new Workflow(this._startExecutorId, this._name, this._description)
        {
            ExecutorBindings = this._executorBindings,
            Edges = this._edges,
            Ports = this._requestPorts,
            OutputExecutors = this._outputExecutors
        };

        // Using the start executor ID as a proxy for the workflow ID
        activity?.SetTag(Tags.WorkflowId, workflow.StartExecutorId);
        if (workflow.Name is not null)
        {
            activity?.SetTag(Tags.WorkflowName, workflow.Name);
        }
        if (workflow.Description is not null)
        {
            activity?.SetTag(Tags.WorkflowDescription, workflow.Description);
        }
        activity?.SetTag(
                Tags.WorkflowDefinition,
                JsonSerializer.Serialize(
                    workflow.ToWorkflowInfo(),
                    WorkflowsJsonUtilities.JsonContext.Default.WorkflowInfo
                )
            );

        return workflow;
    }

    /// <summary>
    /// Builds and returns a workflow instance.
    /// </summary>
    /// <param name="validateOrphans">Specifies whether workflow validation should check for Executor nodes that are
    /// not reachable from the starting executor.</param>
    /// <exception cref="InvalidOperationException">Thrown if there are unbound executors in the workflow definition,
    /// or if the start executor is not bound.</exception>
    public Workflow Build(bool validateOrphans = true)
    {
        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowBuild);

        var workflow = this.BuildInternal(validateOrphans, activity);

        activity?.AddEvent(new ActivityEvent(EventNames.BuildCompleted));

        return workflow;
    }
}
