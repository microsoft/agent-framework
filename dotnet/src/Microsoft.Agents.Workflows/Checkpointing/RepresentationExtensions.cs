// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

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

    public static InputPortInfo ToPortInfo(this InputPort port)
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

    public static WorkflowInfo ToWorkflowInfo<TInput, TResult>(this Workflow<TInput, TResult> workflow)
        => workflow.ToWorkflowInfo(outputType: new TypeId(typeof(TResult)), outputExecutorId: workflow.OutputCollectorId);
}
