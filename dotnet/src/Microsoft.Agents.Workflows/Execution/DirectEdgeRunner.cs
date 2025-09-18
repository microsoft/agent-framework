// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    public IWorkflowContext WorkflowContext { get; } = runContext.Bind(edgeData.SinkId);

    private async ValueTask<Executor> FindRouterAsync(IStepTracer? tracer) => await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, tracer)
                                    .ConfigureAwait(false);

    public async ValueTask<IEnumerable<object?>> ChaseAsync(MessageEnvelope envelope, IStepTracer? tracer)
    {
        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            return [];
        }

        object message = envelope.Message;
        if (this.EdgeData.Condition is not null && !this.EdgeData.Condition(message))
        {
            return [];
        }

        Executor target = await this.FindRouterAsync(tracer).ConfigureAwait(false);
        if (target.CanHandle(envelope.MessageType))
        {
            tracer?.TraceActivated(target.Id);
            return [await target.ExecuteAsync(message, envelope.MessageType, this.WorkflowContext).ConfigureAwait(false)];
        }

        return [];
    }
}
