// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class WorkflowInfo
{
    [JsonConstructor]
    internal WorkflowInfo(
        Dictionary<string, ExecutorInfo> executors,
        Dictionary<string, List<EdgeInfo>> edges,
        HashSet<InputPortInfo> inputPorts,
        TypeId inputType,
        string startExecutorId,
        TypeId? outputType,
        string? outputCollectorId)
    {
        this.Executors = Throw.IfNull(executors);
        this.Edges = Throw.IfNull(edges);
        this.InputPorts = Throw.IfNull(inputPorts);

        this.InputType = Throw.IfNull(inputType);
        this.StartExecutorId = Throw.IfNullOrEmpty(startExecutorId);

        if (outputType is not null && outputCollectorId is not null)
        {
            this.OutputType = outputType;
            this.OutputCollectorId = outputCollectorId;
        }
        else if (outputCollectorId is not null)
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
                !portInfo.RequestType.IsMatch(port.Request) ||
                !portInfo.ResponseType.IsMatch(port.Response)))
        {
            return false;
        }

        return true;
    }

    public bool IsMatch<TInput>(Workflow<TInput> workflow) => this.IsMatch(workflow as Workflow);

    public bool IsMatch<TInput, TResult>(Workflow<TInput, TResult> workflow)
        => this.IsMatch(workflow as Workflow)
           && this.OutputType?.IsMatch(typeof(TResult)) is true
           && this.OutputCollectorId is not null && this.OutputCollectorId == workflow.OutputCollectorId;
}
