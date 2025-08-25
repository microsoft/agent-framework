// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class EdgeMap
{
    private readonly Dictionary<Edge, object> _edgeRunners = new();
    private readonly Dictionary<Edge, FanInEdgeState> _fanInState = new();
    private readonly Dictionary<string, InputEdgeRunner> _portEdgeRunners;
    private readonly InputEdgeRunner _inputRunner;

    public EdgeMap(IRunnerContext runContext,
                   Dictionary<string, HashSet<Edge>> workflowEdges,
                   IEnumerable<InputPort> workflowPorts,
                   string startExecutorId)
    {
        foreach (Edge edge in workflowEdges.Values.SelectMany(e => e))
        {
            object edgeRunner = edge.EdgeType switch
            {
                Edge.Type.Direct => new DirectEdgeRunner(runContext, edge.DirectEdgeData!),
                Edge.Type.FanOut => new FanOutEdgeRunner(runContext, edge.FanOutEdgeData!),
                Edge.Type.FanIn => new FanInEdgeRunner(runContext, edge.FanInEdgeData!),
                _ => throw new NotSupportedException($"Unsupported edge type: {edge.EdgeType}")
            };

            this._edgeRunners[edge] = edgeRunner;
        }

        this._portEdgeRunners = workflowPorts.ToDictionary(
            port => port.Id,
            port => InputEdgeRunner.ForPort(runContext, port)
            );

        this._inputRunner = new InputEdgeRunner(runContext, startExecutorId);
    }

    public async ValueTask<IEnumerable<object?>> InvokeEdgeAsync(Edge edge, string sourceId, MessageEnvelope message)
    {
        if (!this._edgeRunners.TryGetValue(edge, out object? edgeRunner))
        {
            throw new InvalidOperationException($"Edge {edge} not found in the edge map.");
        }

        IEnumerable<object?> edgeResults;
        switch (edge.EdgeType)
        {
            // We know the corresponding EdgeRunner type given the FlowEdge EdgeType, as
            // established in the EdgeMap() ctor; this avoid doing an as-cast inside of
            // the depths of the message delivery loop for every edges (multiplicity N,
            // in FanIn/Out cases)
            // TODO: Once we have a fixed interface, if it is reasonably generalizable
            // between the Runners, we can normalize it behind an IFace.
            case Edge.Type.Direct:
            {
                DirectEdgeRunner runner = (DirectEdgeRunner)this._edgeRunners[edge];
                edgeResults = await runner.ChaseAsync(message).ConfigureAwait(false);
                break;
            }

            case Edge.Type.FanOut:
            {
                FanOutEdgeRunner runner = (FanOutEdgeRunner)this._edgeRunners[edge];
                edgeResults = await runner.ChaseAsync(message).ConfigureAwait(false);
                break;
            }

            case Edge.Type.FanIn:
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
    public async ValueTask<IEnumerable<object?>> InvokeInputAsync(MessageEnvelope envelope)
    {
        return [await this._inputRunner.ChaseAsync(envelope).ConfigureAwait(false)];
    }

    public async ValueTask<IEnumerable<object?>> InvokeResponseAsync(ExternalResponse response)
    {
        if (!this._portEdgeRunners.TryGetValue(response.Port.Id, out InputEdgeRunner? portRunner))
        {
            throw new InvalidOperationException($"Port {response.Port.Id} not found in the edge map.");
        }

        return [await portRunner.ChaseAsync(new MessageEnvelope(response)).ConfigureAwait(false)];
    }
}
