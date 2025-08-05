// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

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
