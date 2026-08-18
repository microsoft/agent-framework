// Copyright (c) Microsoft. All rights reserved.

using System;
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
        string startExecutorId,
        Dictionary<string, HashSet<OutputTag>>? outputExecutorIds)
    {
        this.Executors = Throw.IfNull(executors);
        this.Edges = Throw.IfNull(edges);
        this.RequestPorts = Throw.IfNull(requestPorts);

        this.StartExecutorId = Throw.IfNullOrEmpty(startExecutorId);
        this.OutputExecutorIds = outputExecutorIds ?? new Dictionary<string, HashSet<OutputTag>>(StringComparer.Ordinal);
    }

    public Dictionary<string, ExecutorInfo> Executors { get; }
    public Dictionary<string, List<EdgeInfo>> Edges { get; }
    public HashSet<RequestPortInfo> RequestPorts { get; }

    public TypeId? InputType { get; }
    public string StartExecutorId { get; }

    /// <summary>
    /// Map of executor id to the set of <see cref="OutputTag"/>s under which the executor is registered.
    /// An empty set means the executor is registered as a regular (untagged) output source.
    /// JSON shape: <c>{ "executorId": ["intermediate"], ... }</c>. Legacy payloads using the
    /// older <c>string[]</c> shape are read by <see cref="WorkflowInfoOutputExecutorsConverter"/> and
    /// each id is treated as registered with an empty tag set.
    /// </summary>
    [JsonConverter(typeof(WorkflowInfoOutputExecutorsConverter))]
    public Dictionary<string, HashSet<OutputTag>> OutputExecutorIds { get; }

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
        if (workflow.ExecutorBindings.Count != this.Executors.Count ||
            this.Executors.Keys.Any(
            executorId => workflow.ExecutorBindings.TryGetValue(executorId, out ExecutorBinding? binding)
                       && !this.Executors[executorId].IsMatch(binding)))
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

        // Validate the outputs (key set + tag set per id must match)
        if (workflow.OutputExecutors.Count != this.OutputExecutorIds.Count ||
            this.OutputExecutorIds.Any(kvp =>
                !workflow.OutputExecutors.TryGetValue(kvp.Key, out HashSet<OutputTag>? tags) ||
                tags.Count != kvp.Value.Count ||
                !tags.SetEquals(kvp.Value)))
        {
            return false;
        }

        return true;
    }
}
