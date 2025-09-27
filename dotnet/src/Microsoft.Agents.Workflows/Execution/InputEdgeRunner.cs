// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class InputEdgeRunner(IRunnerContext runContext, string sinkId)
    : EdgeRunner<string>(runContext, sinkId)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(sinkId);

    public static InputEdgeRunner ForPort(IRunnerContext runContext, InputPort port)
    {
        Throw.IfNull(port);

        // The port is an input port, so we can use the port's ID as the sink ID.
        return new InputEdgeRunner(runContext, port.Id);
    }

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        Debug.Assert(envelope.IsExternal, "Input edges should only be chased from external input");
        Executor target = await this.FindExecutorAsync(stepTracer).ConfigureAwait(false);
        if (target.CanHandle(envelope.MessageType))
        {
            return new DeliveryMapping(envelope, target);
        }

        return null;
    }

    private async ValueTask<Executor> FindExecutorAsync(IStepTracer? tracer) => await this.RunContext.EnsureExecutorAsync(this.EdgeData, tracer).ConfigureAwait(false);
}
