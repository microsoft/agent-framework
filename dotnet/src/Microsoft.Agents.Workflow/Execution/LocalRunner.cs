// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

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

internal class LocalRunner<TInput>
{
    public LocalRunner(Workflow<TInput> workflow)
    {
        this.Workflow = workflow ?? throw new ArgumentNullException(nameof(workflow));
        this.RunContext = new LocalRunnerContext<TInput>(workflow);

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.StartExecutorId);
    }

    protected Workflow<TInput> Workflow { get; init; }
    protected LocalRunnerContext<TInput> RunContext { get; init; }
    protected EdgeMap EdgeMap { get; init; }

    // TODO: Better signature?
    public event EventHandler<WorkflowEvent>? WorkflowEvent;

    private void RaiseWorkflowEvent(WorkflowEvent workflowEvent)
    {
        this.WorkflowEvent?.Invoke(this, workflowEvent);
    }

    private bool IsResponse(object message)
    {
        return false;
    }

    private ValueTask<IEnumerable<CallResult?>> RouteExternalMessageAsync(object message)
    {
#pragma warning disable CS0219 // Variable is assigned but its value is never used
        bool isHil = false;
#pragma warning restore CS0219 // Variable is assigned but its value is never used

        return this.IsResponse(message)
            ? this.EdgeMap.InvokeResponseAsync(message)
            : this.EdgeMap.InvokeInputAsync(message);
    }

    public async Task RunAsync(TInput input)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        // Kick everything off by sending the first message to the start executor.
        Executor startExecutor = await this.RunContext.EnsureExecutorAsync(this.Workflow.StartExecutorId)
                                                      .ConfigureAwait(false);

        for (StepContext currentStep = this.RunContext.Advance(); currentStep.HasMessages; currentStep = this.RunContext.Advance())
        {
            // Deliver the messages and queue the next step
            List<Task<IEnumerable<CallResult?>>> edgeTasks = new();
            foreach (Identity sender in currentStep.QueuedMessages.Keys)
            {
                IEnumerable<object> senderMessages = currentStep.QueuedMessages[sender];
                if (sender.Id is null)
                {
                    edgeTasks.AddRange(senderMessages.Select(message => this.RouteExternalMessageAsync(message).AsTask()));
                }
                else
                {
                    HashSet<FlowEdge> outgoingEdges = this.Workflow.Edges[sender.Id!]; // Id is not null when Identity is not .None
                    foreach (FlowEdge outgoingEdge in outgoingEdges)
                    {
                        edgeTasks.AddRange(senderMessages.Select(message => this.EdgeMap.InvokeEdgeAsync(outgoingEdge, sender.Id, message).AsTask()));
                    }
                }
            }

            IEnumerable<CallResult?> results = (await Task.WhenAll(edgeTasks).ConfigureAwait(false)).SelectMany(r => r);

            // After the message handler invocations, we may have some events to deliver
            foreach (WorkflowEvent @event in this.RunContext.QueuedEvents)
            {
                // TODO
            }
        }
    }
}

internal class LocalRunner<TInput, TResult>
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly LocalRunner<TInput> _innerRunner;

    public LocalRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._innerRunner = new LocalRunner<TInput>(workflow);
    }

    public async Task RunAsync(TInput input)
    {
        await this._innerRunner.RunAsync(input).ConfigureAwait(false);
    }

    public TResult? RunningOutput => this._workflow.RunningOutput;
}
