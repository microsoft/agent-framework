// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class EdgeMap
{
    private readonly Dictionary<EdgeId, object> _edgeRunners = [];
    private readonly Dictionary<EdgeId, FanInEdgeState> _fanInState = [];
    private readonly Dictionary<string, InputEdgeRunner> _portEdgeRunners;
    private readonly InputEdgeRunner _inputRunner;
    private readonly IStepTracer? _stepTracer;

    public EdgeMap(IRunnerContext runContext,
                   Dictionary<string, HashSet<Edge>> workflowEdges,
                   IEnumerable<InputPort> workflowPorts,
                   string startExecutorId,
                   IStepTracer? stepTracer = null)
    {
        foreach (Edge edge in workflowEdges.Values.SelectMany(e => e))
        {
            object edgeRunner = edge.Kind switch
            {
                EdgeKind.Direct => new DirectEdgeRunner(runContext, edge.DirectEdgeData!),
                EdgeKind.FanOut => new FanOutEdgeRunner(runContext, edge.FanOutEdgeData!),
                EdgeKind.FanIn => new FanInEdgeRunner(runContext, edge.FanInEdgeData!),
                _ => throw new NotSupportedException($"Unsupported edge type: {edge.Kind}")
            };

            if (edgeRunner is FanInEdgeRunner fanInRunner)
            {
                this._fanInState[edge.Data.Id] = fanInRunner.CreateState();
            }

            this._edgeRunners[edge.Data.Id] = edgeRunner;
        }

        this._portEdgeRunners = workflowPorts.ToDictionary(
            port => port.Id,
            port => InputEdgeRunner.ForPort(runContext, port)
            );

        this._inputRunner = new InputEdgeRunner(runContext, startExecutorId);
        this._stepTracer = stepTracer;
    }

    public async ValueTask<IEnumerable<object?>> InvokeEdgeAsync(Edge edge, string sourceId, MessageEnvelope message)
    {
        EdgeId id = edge.Data.Id;
        if (!this._edgeRunners.TryGetValue(id, out object? edgeRunner))
        {
            throw new InvalidOperationException($"Edge {edge} not found in the edge map.");
        }

        IEnumerable<object?> edgeResults;
        switch (edge.Kind)
        {
            // We know the corresponding EdgeRunner type given the FlowEdge EdgeType, as
            // established in the EdgeMap() ctor; this avoid doing an as-cast inside of
            // the depths of the message delivery loop for every edges (multiplicity N,
            // in FanIn/Out cases)
            // TODO: Once we have a fixed interface, if it is reasonably generalizable
            // between the Runners, we can normalize it behind an IFace.
            case EdgeKind.Direct:
            {
                DirectEdgeRunner runner = (DirectEdgeRunner)edgeRunner;
                edgeResults = await runner.ChaseAsync(message, this._stepTracer).ConfigureAwait(false);
                break;
            }

            case EdgeKind.FanOut:
            {
                FanOutEdgeRunner runner = (FanOutEdgeRunner)edgeRunner;
                edgeResults = await runner.ChaseAsync(message, this._stepTracer).ConfigureAwait(false);
                break;
            }

            case EdgeKind.FanIn:
            {
                FanInEdgeState state = this._fanInState[id];
                FanInEdgeRunner runner = (FanInEdgeRunner)edgeRunner;
                edgeResults = [await runner.ChaseAsync(sourceId, message, state, this._stepTracer).ConfigureAwait(false)];
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
        return [await this._inputRunner.ChaseAsync(envelope, this._stepTracer).ConfigureAwait(false)];
    }

    public async ValueTask<IEnumerable<object?>> InvokeResponseAsync(ExternalResponse response)
    {
        if (!this._portEdgeRunners.TryGetValue(response.PortInfo.PortId, out InputEdgeRunner? portRunner))
        {
            throw new InvalidOperationException($"Port {response.PortInfo.PortId} not found in the edge map.");
        }

        return [await portRunner.ChaseAsync(new MessageEnvelope(response), this._stepTracer).ConfigureAwait(false)];
    }

    internal ValueTask<Dictionary<EdgeId, PortableValue>> ExportStateAsync()
    {
        Dictionary<EdgeId, PortableValue> exportedStates = [];

        // Right now there is only fan-in state
        foreach (EdgeId id in this._fanInState.Keys)
        {
            FanInEdgeState state = this._fanInState[id];
            exportedStates[id] = new PortableValue(state);
        }

        return new(exportedStates);
    }

    internal ValueTask ImportStateAsync(Checkpoint checkpoint)
    {
        Dictionary<EdgeId, PortableValue> importedState = checkpoint.EdgeStateData;

        this._fanInState.Clear();
        foreach (EdgeId id in importedState.Keys)
        {
            PortableValue exportedState = importedState[id];

            FanInEdgeState? fanInState = exportedState.As<FanInEdgeState>();
            if (fanInState is not null)
            {
                this._fanInState[id] = fanInState;
            }
            else
            {
                throw new InvalidOperationException($"Unsupported exported state type: {exportedState.GetType()}; {id}");
            }
        }

        return default;
    }
}
