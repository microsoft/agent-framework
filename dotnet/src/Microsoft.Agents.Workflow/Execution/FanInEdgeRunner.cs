// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

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

        MessageRouter router = sink.Router;
        if (router.CanHandle(message))
        {
            return await router.RouteMessageAsync(message, this.BoundContext)
                                             .ConfigureAwait(false);
        }
        return null;
    }
}
