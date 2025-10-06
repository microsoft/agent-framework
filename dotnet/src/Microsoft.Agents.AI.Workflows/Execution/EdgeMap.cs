// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class EdgeMap
{
    private readonly Dictionary<EdgeId, EdgeRunner> _edgeRunners = [];
    private readonly Dictionary<EdgeId, IStatefulEdgeRunner> _statefulRunners = [];
    private readonly Dictionary<string, ResponseEdgeRunner> _portEdgeRunners;

    private readonly ResponseEdgeRunner _inputRunner;
    private readonly IStepTracer? _stepTracer;

    public EdgeMap(IRunnerContext runContext,
                   Workflow workflow,
                   IStepTracer? stepTracer)
        : this(runContext,
               workflow.Edges,
               workflow.Ports.Values,
               workflow.StartExecutorId,
               stepTracer)
    { }

    public EdgeMap(IRunnerContext runContext,
                   Dictionary<string, HashSet<Edge>> workflowEdges,
                   IEnumerable<RequestPort> workflowPorts,
                   string startExecutorId,
                   IStepTracer? stepTracer = null)
    {
        foreach (Edge edge in workflowEdges.Values.SelectMany(e => e))
        {
            EdgeRunner edgeRunner = edge.Kind switch
            {
                EdgeKind.Direct => new DirectEdgeRunner(runContext, edge.DirectEdgeData!),
                EdgeKind.FanOut => new FanOutEdgeRunner(runContext, edge.FanOutEdgeData!),
                EdgeKind.FanIn => new FanInEdgeRunner(runContext, edge.FanInEdgeData!),
                _ => throw new NotSupportedException($"Unsupported edge type: {edge.Kind}")
            };

            this._edgeRunners[edge.Data.Id] = edgeRunner;

            if (edgeRunner is IStatefulEdgeRunner statefulRunner)
            {
                this._statefulRunners[edge.Data.Id] = statefulRunner;
            }
        }

        this._portEdgeRunners = workflowPorts.ToDictionary(
            port => port.Id,
            port => ResponseEdgeRunner.ForPort(runContext, port)
            );

        this._inputRunner = new ResponseEdgeRunner(runContext, startExecutorId);
        this._stepTracer = stepTracer;
    }

    public ValueTask<DeliveryMapping?> PrepareDeliveryForEdgeAsync(Edge edge, MessageEnvelope message)
    {
        EdgeId id = edge.Data.Id;
        if (!this._edgeRunners.TryGetValue(id, out EdgeRunner? edgeRunner))
        {
            throw new InvalidOperationException($"Edge {edge} not found in the edge map.");
        }

        return edgeRunner.ChaseEdgeAsync(message, this._stepTracer);
    }

    public ValueTask<DeliveryMapping?> PrepareDeliveryForInputAsync(MessageEnvelope message)
    {
        return this._inputRunner.ChaseEdgeAsync(message, this._stepTracer);
    }

    public ValueTask<DeliveryMapping?> PrepareDeliveryForResponseAsync(ExternalResponse response)
    {
        if (!this._portEdgeRunners.TryGetValue(response.PortInfo.PortId, out ResponseEdgeRunner? portRunner))
        {
            throw new InvalidOperationException($"Port {response.PortInfo.PortId} not found in the edge map.");
        }

        return portRunner.ChaseEdgeAsync(new MessageEnvelope(response, ExecutorIdentity.None), this._stepTracer);
    }

    internal async ValueTask<Dictionary<EdgeId, PortableValue>> ExportStateAsync()
    {
        Dictionary<EdgeId, PortableValue> exportedStates = [];

        foreach (EdgeId id in this._statefulRunners.Keys)
        {
            exportedStates[id] = await this._statefulRunners[id].ExportStateAsync().ConfigureAwait(false);
        }

        return exportedStates;
    }

    internal async ValueTask ImportStateAsync(Checkpoint checkpoint)
    {
        Dictionary<EdgeId, PortableValue> importedState = checkpoint.EdgeStateData;

        foreach (EdgeId id in importedState.Keys)
        {
            PortableValue exportedState = importedState[id];
            await this._statefulRunners[id].ImportStateAsync(exportedState).ConfigureAwait(false);
        }
    }
}
