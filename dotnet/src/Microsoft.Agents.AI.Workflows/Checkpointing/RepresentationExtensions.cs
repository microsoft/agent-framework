// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal static class RepresentationExtensions
{
    public static ExecutorInfo ToExecutorInfo(this ExecutorBinding binding)
    {
        Throw.IfNull(binding);
        return new ExecutorInfo(new TypeId(binding.ExecutorType), binding.Id);
    }

    public static EdgeInfo ToEdgeInfo(this Edge edge)
    {
        Throw.IfNull(edge);
        return edge.Kind switch
        {
            EdgeKind.Direct => new DirectEdgeInfo(edge.DirectEdgeData!),
            EdgeKind.FanOut => new FanOutEdgeInfo(edge.FanOutEdgeData!),
            EdgeKind.FanIn => new FanInEdgeInfo(edge.FanInEdgeData!),
            _ => throw new NotSupportedException($"Unsupported edge type: {edge.Kind}")
        };
    }

    public static RequestPortInfo ToPortInfo(this RequestPort port)
    {
        Throw.IfNull(port);
        return new(new TypeId(port.Request), new TypeId(port.Response), port.Id);
    }

    public static WorkflowInfo ToWorkflowInfo(this Workflow workflow)
    {
        Throw.IfNull(workflow);

        Dictionary<string, ExecutorInfo> executors =
            workflow.ExecutorBindings.Values.ToDictionary(
                keySelector: binding => binding.Id,
                elementSelector: ToExecutorInfo);

        Dictionary<string, List<EdgeInfo>> edges = workflow.Edges.Keys.ToDictionary(
            keySelector: sourceId => sourceId,
            elementSelector: sourceId => workflow.Edges[sourceId].Select(ToEdgeInfo).ToList());

        HashSet<RequestPortInfo> inputPorts = new(workflow.Ports.Values.Select(ToPortInfo));

        return new WorkflowInfo(executors, edges, inputPorts, workflow.StartExecutorId, workflow.OutputExecutors);
    }
}
