// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(edgeData.SinkId);

    private async ValueTask<Executor> FindRouterAsync(IStepTracer? tracer) => await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, tracer)
                                    .ConfigureAwait(false);

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            return null;
        }

        object message = envelope.Message;
        if (this.EdgeData.Condition is not null && !this.EdgeData.Condition(message))
        {
            return null;
        }

        Executor target = await this.FindRouterAsync(stepTracer).ConfigureAwait(false);
        if (target.CanHandle(envelope.MessageType))
        {
            return new DeliveryMapping(envelope, target);
        }

        return null;
    }
}
