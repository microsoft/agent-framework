// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal class InputEdgeRunner(IRunnerContext runContext, string sinkId)
    : EdgeRunner<string>(runContext, sinkId)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(sinkId);

    public static InputEdgeRunner ForPort(IRunnerContext runContext, InputPort port)
    {
        Throw.IfNull(port);

        // The port is an input port, so we can use the port's ID as the sink ID.
        return new InputEdgeRunner(runContext, port.Id);
    }

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
