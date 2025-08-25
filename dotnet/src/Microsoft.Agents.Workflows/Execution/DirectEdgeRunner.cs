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

    public async ValueTask<IEnumerable<object?>> ChaseAsync(MessageEnvelope envelope)
    {
        if (envelope.TargetId != null && this.EdgeData.SinkId != envelope.TargetId)
        {
            return [];
        }

        object message = envelope.Message;
        if (this.EdgeData.Condition != null && !this.EdgeData.Condition(message))
        {
            return [];
        }

        Executor target = await this.FindRouterAsync().ConfigureAwait(false);
        if (target.CanHandle(envelope.MessageType))
        {
            return [await target.ExecuteAsync(message, envelope.MessageType, this.WorkflowContext).ConfigureAwait(false)];
        }

        return [];
    }
}
