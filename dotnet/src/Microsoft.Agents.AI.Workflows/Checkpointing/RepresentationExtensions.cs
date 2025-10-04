// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal static class RepresentationExtensions
{
    public static ExecutorInfo ToExecutorInfo(this ExecutorRegistration registration)
    {
        Throw.IfNull(registration);
        return new ExecutorInfo(new TypeId(registration.ExecutorType), registration.Id);
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

    private static WorkflowInfo ToWorkflowInfo(this Workflow workflow, TypeId? inputType, TypeId? outputType, string? outputExecutorId)
    {
        Throw.IfNull(workflow);

        Dictionary<string, ExecutorInfo> executors =
            workflow.Registrations.Values.ToDictionary(
                keySelector: registration => registration.Id,
                elementSelector: ToExecutorInfo);

        Dictionary<string, List<EdgeInfo>> edges = workflow.Edges.Keys.ToDictionary(
            keySelector: sourceId => sourceId,
            elementSelector: sourceId => workflow.Edges[sourceId].Select(ToEdgeInfo).ToList());

        HashSet<RequestPortInfo> inputPorts = new(workflow.Ports.Values.Select(ToPortInfo));

        return new WorkflowInfo(executors, edges, inputPorts, inputType, workflow.StartExecutorId, workflow.OutputExecutors);
    }

    public static WorkflowInfo ToWorkflowInfo(this Workflow workflow)
        => workflow.ToWorkflowInfo(inputType: null, outputType: null, outputExecutorId: null);

    public static WorkflowInfo ToWorkflowInfo<TInput>(this Workflow<TInput> workflow)
        => workflow.ToWorkflowInfo(inputType: new(workflow.InputType), outputType: null, outputExecutorId: null);
}
