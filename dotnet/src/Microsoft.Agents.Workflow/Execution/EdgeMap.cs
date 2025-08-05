// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal class EdgeMap
{
    private readonly Dictionary<FlowEdge, object> _edgeRunners = new();
    private readonly Dictionary<FlowEdge, FanInEdgeState> _fanInState = new();
    private readonly InputEdgeRuner _inputRunner;

    public EdgeMap(IRunnerContext runContext, Dictionary<string, HashSet<FlowEdge>> workflowEdges, string startExecutorId)
    {
        foreach (FlowEdge edge in workflowEdges.Values.SelectMany(e => e))
        {
            object edgeRunner = edge.EdgeType switch
            {
                FlowEdge.Type.Direct => new DirectEdgeRunner(runContext, edge.DirectEdgeData!),
                FlowEdge.Type.FanOut => new FanOutEdgeRunner(runContext, edge.FanOutEdgeData!),
                FlowEdge.Type.FanIn => new FanInEdgeRunner(runContext, edge.FanInEdgeData!),
                _ => throw new NotSupportedException($"Unsupported edge type: {edge.EdgeType}")
            };

            this._edgeRunners[edge] = edgeRunner;
        }

        this._inputRunner = new InputEdgeRuner(runContext, startExecutorId);
    }

    public async ValueTask<IEnumerable<CallResult?>> InvokeEdgeAsync(FlowEdge edge, string sourceId, object message)
    {
        if (!this._edgeRunners.TryGetValue(edge, out object? edgeRunner))
        {
            throw new InvalidOperationException($"Edge {edge} not found in the edge map.");
        }

        IEnumerable<CallResult?> edgeResults;
        switch (edge.EdgeType)
        {
            // We know the corresponding EdgeRunner type given the FlowEdge EdgeType, as
            // established in the EdgeMap() ctor; this avoid doing an as-cast inside of
            // the depths of the message delivery loop for every edges (multiplicity N,
            // in FanIn/Out cases)
            // TODO: Once we have a fixed interface, if it is reasonably generalizable
            // between the Runners, we can normalize it behind an IFace.
            case FlowEdge.Type.Direct:
            {
                DirectEdgeRunner runner = (DirectEdgeRunner)this._edgeRunners[edge];
                edgeResults = await runner.ChaseAsync(message).ConfigureAwait(false);
                break;
            }

            case FlowEdge.Type.FanOut:
            {
                FanOutEdgeRunner runner = (FanOutEdgeRunner)this._edgeRunners[edge];
                edgeResults = await runner.ChaseAsync(message).ConfigureAwait(false);
                break;
            }

            case FlowEdge.Type.FanIn:
            {
                FanInEdgeState state = this._fanInState[edge];
                FanInEdgeRunner runner = (FanInEdgeRunner)this._edgeRunners[edge];
                edgeResults = [await runner.ChaseAsync(sourceId, message, state).ConfigureAwait(false)];
                break;
            }

            default:
                throw new InvalidOperationException("Unknown edge type");

        }

        return edgeResults;
    }

    // TODO: Should we promote Input to a true "FlowEdge" type?
    public async ValueTask<IEnumerable<CallResult?>> InvokeInputAsync(object inputMessage)
    {
        return [await this._inputRunner.ChaseAsync(inputMessage).ConfigureAwait(false)];
    }

    public ValueTask<IEnumerable<CallResult?>> InvokeResponseAsync(object externalResponse)
    {
        throw new NotImplementedException();
    }
}
