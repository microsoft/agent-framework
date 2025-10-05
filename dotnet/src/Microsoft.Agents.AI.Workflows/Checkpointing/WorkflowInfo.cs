// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal sealed class WorkflowInfo
{
    [JsonConstructor]
    internal WorkflowInfo(
        Dictionary<string, ExecutorInfo> executors,
        Dictionary<string, List<EdgeInfo>> edges,
        HashSet<RequestPortInfo> requestPorts,
        TypeId? inputType,
        string startExecutorId,
        HashSet<string>? outputExecutorIds)
    {
        this.Executors = Throw.IfNull(executors);
        this.Edges = Throw.IfNull(edges);
        this.RequestPorts = Throw.IfNull(requestPorts);

        this.InputType = inputType;
        this.StartExecutorId = Throw.IfNullOrEmpty(startExecutorId);
        this.OutputExecutorIds = outputExecutorIds ?? [];
    }

    public Dictionary<string, ExecutorInfo> Executors { get; }
    public Dictionary<string, List<EdgeInfo>> Edges { get; }
    public HashSet<RequestPortInfo> RequestPorts { get; }

    public TypeId? InputType { get; }
    public string StartExecutorId { get; }

    public HashSet<string> OutputExecutorIds { get; }

    public bool IsMatch(Workflow workflow)
    {
        if (workflow is null)
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
        if (workflow.Ports.Count != this.RequestPorts.Count ||
            this.RequestPorts.Any(portInfo =>
                !workflow.Ports.TryGetValue(portInfo.PortId, out RequestPort? port) ||
                !portInfo.RequestType.IsMatch(port.Request) ||
                !portInfo.ResponseType.IsMatch(port.Response)))
        {
            return false;
        }

        // Validate the outputs
        if (workflow.OutputExecutors.Count != this.OutputExecutorIds.Count ||
            this.OutputExecutorIds.Any(id => !workflow.OutputExecutors.Contains(id)))
        {
            return false;
        }

        return true;
    }

    public bool IsMatch<TInput>(Workflow<TInput> workflow) =>
        this.IsMatch(workflow as Workflow) && this.InputType?.IsMatch<TInput>() == true;
}
