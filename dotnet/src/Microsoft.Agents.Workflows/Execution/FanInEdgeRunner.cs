// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData)
{
    private IWorkflowContext BoundContext { get; } = runContext.Bind(edgeData.SinkId);

    public FanInEdgeState CreateState() => new(this.EdgeData);

    public async ValueTask<object?> ChaseAsync(string sourceId, object message, FanInEdgeState state)
    {
        IEnumerable<object>? releasedMessages = state.ProcessMessage(sourceId, message);
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            return null;
        }

        Executor target = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId)
                                                   .ConfigureAwait(false);

        if (target.CanHandle(message.GetType()))
        {
            return await target.ExecuteAsync(message, this.BoundContext)
                               .ConfigureAwait(false);
        }
        return null;
    }
}
