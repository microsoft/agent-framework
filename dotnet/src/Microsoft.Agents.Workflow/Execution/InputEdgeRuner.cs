// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal class InputEdgeRuner(IRunnerContext runContext, string sinkId)
    : EdgeRunner<string>(runContext, sinkId)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(sinkId);

    private async ValueTask<MessageRouter> FindRouterAsync()
    {
        Executor sink = await this.RunContext.EnsureExecutorAsync(this.EdgeData)
                                             .ConfigureAwait(false);

        return sink.Router;
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
