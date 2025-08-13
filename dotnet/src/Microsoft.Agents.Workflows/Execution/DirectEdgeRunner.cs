// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(edgeData.SinkId);

    private async ValueTask<Executor> FindRouterAsync()
    {
        return await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId)
                                    .ConfigureAwait(false);
    }

    public async ValueTask<IEnumerable<object?>> ChaseAsync(object message)
    {
        if (this.EdgeData.Condition != null && !this.EdgeData.Condition(message))
        {
            return [];
        }

        Executor target = await this.FindRouterAsync().ConfigureAwait(false);
        if (target.CanHandle(message.GetType()))
        {
            return [await target.ExecuteAsync(message, this.WorkflowContext).ConfigureAwait(false)];
        }

        return [];
    }
}
