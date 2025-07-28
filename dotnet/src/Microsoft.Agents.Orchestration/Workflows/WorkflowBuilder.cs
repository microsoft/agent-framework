// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.Orchestration.Workflows.Core;
#pragma warning restore IDE0005 // Using directive is unnecessary.

using ConditionalT = System.Func<object?, bool>;

namespace Microsoft.Agents.Orchestration.Workflows;

internal delegate TExecutor ExecutorProvider<out TExecutor>()
    where TExecutor : Executor;

internal struct EdgeKey : IEquatable<EdgeKey>
{
    public string SourceId { get; init; }
    public string TargetId { get; init; }

    public EdgeKey(string sourceId, string targetId)
    {
        this.SourceId = sourceId ?? throw new ArgumentNullException(nameof(sourceId));
        this.TargetId = targetId ?? throw new ArgumentNullException(nameof(targetId));
    }

    public bool Equals(EdgeKey other) => this.SourceId == other.SourceId && this.TargetId == other.TargetId;
    public override bool Equals(object? obj) => obj is EdgeKey other && this.Equals(other);
    public override int GetHashCode() => HashCode.Combine(this.SourceId, this.TargetId);
}

/// <summary>
/// .
/// </summary>
public class ExecutionResult
{
}

internal sealed class ExecutorIsh :
    IIdentified,
    IEquatable<ExecutorIsh>,
    IEquatable<IIdentified>,
    IEquatable<string>
{
    public enum Type
    {
        Unbound,
        Executor,
        //Function,
        //Agent,
        //ProcessStep
    }

    public Type ExecutorType { get; init; }

    private readonly string? _idValue;
    private readonly Executor? _executorValue;
    //private readonly Func<object?, CallResult>? _functionValue;

    public ExecutorIsh(Executor executor)
    {
        this.ExecutorType = Type.Executor;
        this._executorValue = executor ?? throw new ArgumentNullException(nameof(executor));
    }

    public ExecutorIsh(string id)
    {
        this.ExecutorType = Type.Unbound;
        this._idValue = id ?? throw new ArgumentNullException(nameof(id));
    }

    public bool IsUnbound => this.ExecutorType == Type.Unbound;

    public string Id => this.ExecutorType switch
    {
        Type.Unbound => this._idValue ?? throw new InvalidOperationException("This ExecutorIsh is unbound and has no ID."),
        Type.Executor => this._executorValue!.Id,
        //Type.Function => throw new NotImplementedException("Function type is not yet implemented."),
        //Type.Agent => throw new NotImplementedException("Agent type is not yet implemented."),
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
    };

    public ExecutorProvider<Executor> ExecutorProvider => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"Executor with ID '{this.Id}' is unbound."),
        Type.Executor => () => this._executorValue!,
        //Type.Function => throw new NotImplementedException("Function type is not yet implemented."),
        //Type.Agent => throw new NotImplementedException("Agent type is not yet implemented."),
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
    };

    //public ExecutorIsh(Func<object?, CallResult> function)
    //{
    //    this.ExecutorType = Type.Function;
    //    this._functionValue = function ?? throw new ArgumentNullException(nameof(function));
    //}

    // Implicit conversions into ExecutorIsh
    public static implicit operator ExecutorIsh(Executor executor)
    {
        return new ExecutorIsh(executor);
    }

    // How do we AoT compile this?
    //public static implicit operator ExecutorIsh(Func<object?, CallResult> function)
    //{
    //    return new ExecutorIsh(function);
    //}

    public static implicit operator ExecutorIsh(string id)
    {
        return new ExecutorIsh(id);
    }

    public bool Equals(ExecutorIsh? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    public bool Equals(IIdentified? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    public bool Equals(string? other)
    {
        return other is not null &&
               other == this.Id;
    }

    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is ExecutorIsh ish)
        {
            return this.Equals(ish);
        }
        else if (obj is IIdentified identified)
        {
            return this.Equals(identified);
        }
        else if (obj is string str)
        {
            return this.Equals(str);
        }

        return false;
    }

    public override int GetHashCode()
    {
        return this.Id.GetHashCode();
    }

    public override string ToString()
    {
        return this.ExecutorType switch
        {
            Type.Unbound => $"'{this.Id}':<unbound>",
            Type.Executor => $"'{this.Id}':{this._executorValue!.GetType()}",
            //Type.Function => $"ExecutorIsh for Function with ID '{this.Id}'",
            //Type.Agent => $"ExecutorIsh for Agent with ID '{this.Id}'",
            //Type.ProcessStep => $"ExecutorIsh for ProcessStep with ID '{this.Id}'",
            _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
        };
    }
}

internal class FlowEdge(ExecutorIsh source, ExecutorIsh sink, ConditionalT? conditional) : IEquatable<FlowEdge>
{
    public ExecutorIsh Source { get; init; } = source ?? throw new ArgumentNullException(nameof(source));
    public ExecutorIsh Sink { get; } = sink ?? throw new ArgumentNullException(nameof(sink));
    public Func<object?, bool>? Condition { get; } = conditional;

    public bool Equals(FlowEdge? other)
    {
        return other is null
                    ? false
                    : this.Source.Equals(other.Source) && this.Sink.Equals(other.Sink);
    }

    public override bool Equals(object? obj) => obj is FlowEdge other && this.Equals(other);
    public override int GetHashCode() => HashCode.Combine(this.Source.GetHashCode(), this.Sink.GetHashCode());
}

internal class Workflow
{
    public Dictionary<string, ExecutorProvider<Executor>> Executors { get; internal init; } = new();
    public Dictionary<string, HashSet<FlowEdge>> Edges { get; internal init; } = new();

#if NET9_0_OR_GREATER
    required
#endif
    public string StartExecutorId
    { get; init; }

#if NET9_0_OR_GREATER
    required
#endif
    public Type InputType
    { get; init; } = typeof(object);

    public Workflow(string startExecutorId, Type type)
    {
        this.StartExecutorId = startExecutorId ?? throw new ArgumentNullException(nameof(startExecutorId));
        this.InputType = type ?? throw new ArgumentNullException(nameof(type));

        // TODO: How do we (1) ensure the types are happy, and (2) work under AOT?
    }

#if NET9_0_OR_GREATER
    public Workflow()
    { }
#endif
}

// Just a decorator for the purposes of keeping type type where we can
internal class Workflow<T> : Workflow
{
    public Workflow(string startExecutorId) : base(startExecutorId, typeof(T))
    {
    }

#if NET9_0_OR_GREATER
    public Workflow()
    {
        this.InputType = typeof(T);
    }
#endif
}

internal class WorkflowBuilder
{
    private readonly Dictionary<string, ExecutorProvider<Executor>> _executors = new();
    private readonly Dictionary<string, HashSet<FlowEdge>> _edges = new();
    private readonly HashSet<string> _unboundExecutors = new();

    private readonly string _startExecutorId;

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

    public WorkflowBuilder AddEdge(ExecutorIsh source, ExecutorIsh target, Func<object?, bool>? condition = null)
    {
        // Add an edge from source to target with an optional condition.
        // This is a low-level builder method that does not enforce any specific executor type.
        // The condition can be used to determine if the edge should be followed based on the input.

        if (source == null)
        {
            throw new ArgumentNullException(nameof(source));
        }

        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        if (!this._edges.TryGetValue(source.Id, out HashSet<FlowEdge>? edges))
        {
            edges = new HashSet<FlowEdge>();
            this._edges[source.Id] = edges;
        }

        edges.Add(new FlowEdge(this.Track(source), this.Track(target), condition));
        return this;
    }

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
        }

        return new Workflow<T>(this._startExecutorId) // Why does it not see the default ctor?
        {
            Executors = this._executors,
            Edges = this._edges,
            StartExecutorId = this._startExecutorId,
            InputType = typeof(T)
        };
    }
}
