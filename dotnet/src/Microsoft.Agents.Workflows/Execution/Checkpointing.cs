// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal interface ICheckpointingRunner
{
    // TODO: Convert this to a multi-timeline (e.g.: Live timeline + forks for orphaned checkpoints due to timetravel)
    IReadOnlyList<CheckpointInfo> Checkpoints { get; }

    ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo);
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="TRun"></typeparam>
public class Checkpointed<TRun>
{
    internal Checkpointed(TRun run, ICheckpointingRunner runner)
    {
        this.Run = Throw.IfNull(run);
        this._runner = Throw.IfNull(runner);
    }

    private readonly ICheckpointingRunner _runner;

    /// <summary>
    /// .
    /// </summary>
    public TRun Run { get; }

    /// <inheritdoc cref="ICheckpointingRunner.Checkpoints"/>
    public IReadOnlyList<CheckpointInfo> Checkpoints => this._runner.Checkpoints;

    /// <summary>
    /// Gets the most recent checkpoint information.
    /// </summary>
    public CheckpointInfo? LastCheckpoint => this.Checkpoints[this.Checkpoints.Count];

    /// <inheritdoc cref="ICheckpointingRunner.RestoreCheckpointAsync"/>
    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo)
        => this._runner.RestoreCheckpointAsync(checkpointInfo);
}

/// <summary>
/// .
/// </summary>
public sealed class CheckpointManager : ICheckpointManager
{
    private readonly Dictionary<CheckpointInfo, Checkpoint> _checkpoints = new();

    ValueTask<CheckpointInfo> ICheckpointManager.CommitCheckpointAsync(Checkpoint checkpoint)
    {
        Throw.IfNull(checkpoint);

        this._checkpoints[checkpoint] = checkpoint;
        return new(checkpoint);
    }

    ValueTask<Checkpoint> ICheckpointManager.LookupCheckpointAsync(CheckpointInfo checkpointInfo)
    {
        Throw.IfNull(checkpointInfo);

        if (!this._checkpoints.TryGetValue(checkpointInfo, out Checkpoint? checkpoint))
        {
            throw new KeyNotFoundException($"Checkpoint not found: {checkpointInfo}");
        }

        return new ValueTask<Checkpoint>(checkpoint);
    }
}

internal class ExportedState(object state)
{
    public Type RuntimeType => Throw.IfNull(state).GetType();
    public object Value => Throw.IfNull(state);
}

internal static class Representation
{
    public class TypeId(Type type)
    {
        public string AssemblyName => Throw.IfNull(type.Assembly.FullName);
        public string TypeName => Throw.IfNull(type.FullName);

        public bool IsMatch(Type type)
        {
            return this.AssemblyName == type.Assembly.FullName
                && this.TypeName == type.FullName;
        }

        public bool IsMatch<T>() => this.IsMatch(typeof(T));
    }

    public record class ExecutorInfo(TypeId ExecutorType, string ExecutorId)
    {
        public bool IsMatch<T>() where T : Executor
        {
            return this.ExecutorType.IsMatch<T>()
                && this.ExecutorId == typeof(T).Name;
        }

        public bool IsMatch(Executor executor)
        {
            return this.ExecutorType.IsMatch(executor.GetType())
                && this.ExecutorId == executor.Id;
        }

        public bool IsMatch(ExecutorRegistration registration)
        {
            return this.ExecutorType.IsMatch(registration.ExecutorType)
                && this.ExecutorId == registration.Id;
        }
    }

    private static ExecutorInfo ToExecutorInfo(this ExecutorRegistration registration)
    {
        Throw.IfNull(registration);
        return new ExecutorInfo(new TypeId(registration.ExecutorType), registration.Id);
    }

    public abstract class EdgeInfo(Edge.Type edgeType, EdgeConnection connection)
    {
        public Edge.Type EdgeType => edgeType;
        public EdgeConnection Connection { get; } = Throw.IfNull(connection);

        public bool IsMatch(Edge edge)
        {
            return this.EdgeType == edge.EdgeType
                && this.Connection.Equals(edge.Data.Connection)
                && this.IsMatchInternal(edge.Data);
        }

        protected virtual bool IsMatchInternal(EdgeData edgeData) => true;
    }

    public class DirectEdgeInfo(DirectEdgeData data) : EdgeInfo(Edge.Type.Direct, data.Connection)
    {
        public bool HasCondition => data.Condition != null;

        protected override bool IsMatchInternal(EdgeData edgeData)
        {
            return edgeData is DirectEdgeData directEdge
                && this.HasCondition == (directEdge.Condition != null);
        }
    }

    public class FanOutEdgeInfo(FanOutEdgeData data) : EdgeInfo(Edge.Type.FanOut, data.Connection)
    {
        public bool HasAssigner => data.EdgeAssigner != null;

        protected override bool IsMatchInternal(EdgeData edgeData)
        {
            return edgeData is FanOutEdgeData fanOutEdge
                && this.HasAssigner == (fanOutEdge.EdgeAssigner != null);
        }
    }

    public class FanInEdgeInfo(FanInEdgeData data) : EdgeInfo(Edge.Type.FanIn, data.Connection);

    private static EdgeInfo ToEdgeInfo(this Edge edge)
    {
        Throw.IfNull(edge);
        return edge.EdgeType switch
        {
            Edge.Type.Direct => new DirectEdgeInfo(edge.DirectEdgeData!),
            Edge.Type.FanOut => new FanOutEdgeInfo(edge.FanOutEdgeData!),
            Edge.Type.FanIn => new FanInEdgeInfo(edge.FanInEdgeData!),
            _ => throw new NotSupportedException($"Unsupported edge type: {edge.EdgeType}")
        };
    }

    public record class InputPortInfo(TypeId InputType, TypeId OutputType, string PortId);

    private static InputPortInfo ToPortInfo(this InputPort port)
    {
        Throw.IfNull(port);
        return new(new TypeId(port.Request), new TypeId(port.Response), port.Id);
    }

    private static WorkflowInfo ToWorkflowInfo<TInput>(this Workflow<TInput> workflow, TypeId? outputType, string? outputExecutorId)
    {
        Throw.IfNull(workflow);

        Dictionary<string, ExecutorInfo> executors =
            workflow.Registrations.Values.ToDictionary(
                keySelector: registration => registration.Id,
                elementSelector: ToExecutorInfo);

        Dictionary<string, List<EdgeInfo>> edges = workflow.Edges.Keys.ToDictionary(
            keySelector: sourceId => sourceId,
            elementSelector: sourceId => workflow.Edges[sourceId].Select(ToEdgeInfo).ToList());

        HashSet<InputPortInfo> inputPorts = new(workflow.Ports.Values.Select(ToPortInfo));

        return new WorkflowInfo(executors, edges, inputPorts, new TypeId(workflow.InputType), workflow.StartExecutorId, outputType, outputExecutorId);
    }

    public static WorkflowInfo ToWorkflowInfo<TInput>(this Workflow<TInput> workflow)
        => workflow.ToWorkflowInfo(outputType: null, outputExecutorId: null);

    public static WorkflowInfo GetInfo<TInput, TResult>(this Workflow<TInput, TResult> workflow)
        => workflow.ToWorkflowInfo(outputType: new TypeId(typeof(TResult)), outputExecutorId: workflow.OutputCollectorId);

    public class WorkflowInfo
    {
        internal WorkflowInfo(
            Dictionary<string, ExecutorInfo> executors,
            Dictionary<string, List<EdgeInfo>> edges,
            HashSet<InputPortInfo> inputPorts,
            TypeId inputType,
            string startExecutorId,
            TypeId? outputType = null,
            string? outputCollectorId = null)
        {
            this.Executors = Throw.IfNull(executors);
            this.Edges = Throw.IfNull(edges);
            this.InputPorts = Throw.IfNull(inputPorts);

            this.InputType = Throw.IfNull(inputType);
            this.StartExecutorId = Throw.IfNullOrEmpty(startExecutorId);

            if (this.OutputType != null && this.OutputCollectorId != null)
            {
                this.OutputType = outputType;
                this.OutputCollectorId = outputCollectorId;
            }
            else if (this.OutputCollectorId != null)
            {
                throw new InvalidOperationException(
                    $"Either both or none of OutputType and OutputCollectorId must be set. ({nameof(outputType)}: {outputType} vs. {nameof(outputCollectorId)}: {outputCollectorId})"
                );
            }
        }

        public Dictionary<string, ExecutorInfo> Executors { get; }
        public Dictionary<string, List<EdgeInfo>> Edges { get; }
        public HashSet<InputPortInfo> InputPorts { get; }

        public TypeId InputType { get; }
        public string StartExecutorId { get; }

        public TypeId? OutputType { get; }
        public string? OutputCollectorId { get; }

        private bool IsMatch(Workflow workflow)
        {
            if (workflow is null)
            {
                return false;
            }

            if (!this.InputType.IsMatch(workflow.InputType))
            {
                return false;
            }

            if (this.StartExecutorId != workflow.StartExecutorId)
            {
                return false;
            }

            // Validate the executors
            if (workflow.Registrations.Count != this.Executors.Count ||
                this.Executors.Keys.Any(
                executorId => workflow.Registrations.TryGetValue(executorId, out ExecutorRegistration? registration)
                           && !this.Executors[executorId].IsMatch(registration)))
            {
                return false;
            }

            // Validate the edges
            if (workflow.Edges.Count != this.Edges.Count ||
                this.Edges.Keys.Any(
                    sourceId =>
                        // If the sourceId is not present in the workflow edges, or
                        !workflow.Edges.TryGetValue(sourceId, out var edgeList) ||
                        // If the edge list count does not match, or
                        edgeList.Count != this.Edges[sourceId].Count ||
                        // If any edge in the workflow edge list does not match the corresponding edge in this.Edges[sourceId]
                        !edgeList.All(edge => this.Edges[sourceId].Any(e => e.IsMatch(edge)))
                ))
            {
                return false;
            }

            // Validate the input ports
            if (workflow.Ports.Count != this.InputPorts.Count ||
                this.InputPorts.Any(portInfo =>
                    !workflow.Ports.TryGetValue(portInfo.PortId, out InputPort? port) ||
                    !portInfo.InputType.IsMatch(port.Request) ||
                    !portInfo.OutputType.IsMatch(port.Response)))
            {
                return false;
            }

            return true;
        }

        public bool IsMatch<TInput>(Workflow<TInput> workflow) => this.IsMatch(workflow as Workflow);

        public bool IsMatch<TInput, TResult>(Workflow<TInput, TResult> workflow)
            => this.IsMatch(workflow as Workflow)
               && this.OutputType != null && this.OutputType.IsMatch(typeof(TResult))
               && this.OutputCollectorId != null && this.OutputCollectorId == workflow.OutputCollectorId;
    }
}

/// <summary>
/// Represents a checkpoint with a unique identifier and a timestamp indicating when it was created.
/// </summary>
public class CheckpointInfo : IEquatable<CheckpointInfo>
{
    /// <summary>
    /// The unique identifier for the checkpoint.
    /// </summary>
    public string CheckpointId { get; } = Guid.NewGuid().ToString("N");

    /// <summary>
    /// The date and time when the object was created, in Coordinated Universal Time (UTC).
    /// </summary>
    public DateTimeOffset CreatedAt { get; } = DateTimeOffset.UtcNow;

    /// <inheritdoc/>
    public bool Equals(CheckpointInfo? other)
    {
        if (other == null)
        {
            return false;
        }

        return this.CheckpointId == other.CheckpointId &&
               this.CreatedAt == other.CreatedAt;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return this.Equals(obj as CheckpointInfo);
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        return HashCode.Combine(this.CheckpointId, this.CreatedAt);
    }

    /// <inheritdoc/>
    public override string ToString() => $"CheckpointId: {this.CheckpointId}, CreatedAt: {this.CreatedAt:O}";
}

/// <summary>
/// .
/// </summary>
internal class Checkpoint : CheckpointInfo
{
    internal Checkpoint(
        Representation.WorkflowInfo workflow,
        RunnerCheckpointData runnerData,
        Dictionary<ScopeKey, ExportedState> stateData,
        Dictionary<EdgeConnection, ExportedState> edgeStateData)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunnerData = Throw.IfNull(runnerData);
        this.State = Throw.IfNull(stateData);
        this.EdgeState = Throw.IfNull(edgeStateData);
    }

    public Representation.WorkflowInfo Workflow { get; }
    public RunnerCheckpointData RunnerData { get; }

    public readonly Dictionary<ScopeKey, ExportedState> State = new();
    public readonly Dictionary<EdgeConnection, ExportedState> EdgeState = new();
}

//internal interface ISerializer
//{
//    ValueTask<Checkpoint> DeserializeAsync(Stream stream);
//    ValueTask SerializeAsync(Stream stream, Checkpoint checkpoint);
//}
