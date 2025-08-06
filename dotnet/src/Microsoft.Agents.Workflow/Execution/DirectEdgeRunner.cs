// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(edgeData.SinkId);

    private async ValueTask<MessageRouter> FindRouterAsync()
    {
        Executor sink = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId)
                                             .ConfigureAwait(false);

        return sink.Router;
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
