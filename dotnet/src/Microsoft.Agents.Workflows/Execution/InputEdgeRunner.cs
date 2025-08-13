// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
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

    private async ValueTask<Executor> FindExecutorAsync()
    {
        return await this.RunContext.EnsureExecutorAsync(this.EdgeData).ConfigureAwait(false);
    }

    public async ValueTask<object?> ChaseAsync(object message)
    {
        Executor target = await this.FindExecutorAsync().ConfigureAwait(false);
        if (target.CanHandle(message.GetType()))
        {
            return await target.ExecuteAsync(message, this.WorkflowContext)
                               .ConfigureAwait(false);
        }

        // TODO: Throw instead?

        return null;
    }
}
