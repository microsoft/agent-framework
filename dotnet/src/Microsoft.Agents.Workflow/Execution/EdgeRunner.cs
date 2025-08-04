// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal abstract class EdgeRunner<TEdgeData>(
    IRunnerContext runContext, TEdgeData edgeData)
{
    protected IRunnerContext RunContext { get; } = Throw.IfNull(runContext);
    protected TEdgeData EdgeData { get; } = Throw.IfNull(edgeData);
}

internal class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(edgeData.SinkId);

    private async ValueTask<MessageRouter> FindRouterAsync()
    {
        Executor sink = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId)
                                             .ConfigureAwait(false);

        return sink.MessageRouter;
    }

    public async ValueTask<IEnumerable<CallResult?>> ChaseAsync(object message)
    {
        if (this.EdgeData.Condition != null && !this.EdgeData.Condition(message))
        {
            return [];
        }

        MessageRouter router = await this.FindRouterAsync().ConfigureAwait(false);
        if (router.CanHandle(message))
        {
            return [await router.RouteMessageAsync(message, this.WorkflowContext)
                                             .ConfigureAwait(false)];
        }

        return [];
    }
}

internal class FanOutEdgeRunner(IRunnerContext runContext, FanOutEdgeData edgeData) :
    EdgeRunner<FanOutEdgeData>(runContext, edgeData)
{
    private Dictionary<string, IWorkflowContext> BoundContexts { get; }
        = edgeData.SinkIds.ToDictionary(
            sinkId => sinkId,
            sinkId => runContext.Bind(sinkId));

    public async ValueTask<IEnumerable<CallResult?>> ChaseAsync(object message)
    {
        List<string> targets =
            this.EdgeData.Partitioner == null
                ? this.EdgeData.SinkIds
                : this.EdgeData.Partitioner(message, this.BoundContexts.Count).Select(i => this.EdgeData.SinkIds[i]).ToList();

        CallResult?[] result = await Task.WhenAll(targets.Select(ProcessTargetAsync)).ConfigureAwait(false);
        return result.Where(r => r is not null);

        async Task<CallResult?> ProcessTargetAsync(string targetId)
        {
            Executor executor = await this.RunContext.EnsureExecutorAsync(targetId)
                                                     .ConfigureAwait(false);

            MessageRouter router = executor.MessageRouter;
            if (router.CanHandle(message))
            {
                return await router.RouteMessageAsync(message, this.BoundContexts[targetId])
                                   .ConfigureAwait(false);
            }

            return null;
        }
    }
}

internal record FanInEdgeState(FanInEdgeData EdgeData)
{
    private List<object>? _pendingMessages
        = EdgeData.Trigger == FanInTrigger.WhenAll ? [] : null;

    private HashSet<string>? _unseen
        = EdgeData.Trigger == FanInTrigger.WhenAll ? new(EdgeData.SourceIds) : null;

    public IEnumerable<object>? ProcessMessage(string sourceId, object message)
    {
        if (this.EdgeData.Trigger == FanInTrigger.WhenAll)
        {
            this._pendingMessages!.Add(message);
            this._unseen!.Remove(sourceId);

            if (this._unseen.Count == 0)
            {
                List<object> result = this._pendingMessages;

                this._pendingMessages = [];
                this._unseen = new(this.EdgeData.SourceIds);

                return result;
            }

            return null;
        }

        return [message];
    }
}

internal class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData)
{
    private IWorkflowContext BoundContext { get; } = runContext.Bind(edgeData.SinkId);

    public FanInEdgeState CreateState() => new(this.EdgeData);

    public async ValueTask<CallResult?> ChaseAsync(string sourceId, object message, FanInEdgeState state)
    {
        IEnumerable<object>? releasedMessages = state.ProcessMessage(sourceId, message);
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            return null;
        }

        Executor sink = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId)
                                             .ConfigureAwait(false);

        MessageRouter router = sink.MessageRouter;
        if (router.CanHandle(message))
        {
            return await router.RouteMessageAsync(message, this.BoundContext)
                                             .ConfigureAwait(false);
        }
        return null;
    }
}

internal class InputEdgeRuner(IRunnerContext runContext, string sinkId)
    : EdgeRunner<string>(runContext, sinkId)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(sinkId);

    private async ValueTask<MessageRouter> FindRouterAsync()
    {
        Executor sink = await this.RunContext.EnsureExecutorAsync(this.EdgeData)
                                             .ConfigureAwait(false);

        return sink.MessageRouter;
    }

    public async ValueTask<CallResult?> ChaseAsync(object message)
    {
        MessageRouter router = await this.FindRouterAsync().ConfigureAwait(false);
        if (router.CanHandle(message))
        {
            return await router.RouteMessageAsync(message, this.WorkflowContext)
                                             .ConfigureAwait(false);
        }

        // TODO: Throw instead?

        return null;
    }
}
