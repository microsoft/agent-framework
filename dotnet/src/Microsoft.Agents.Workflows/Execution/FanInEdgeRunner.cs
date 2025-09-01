// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData)
{
    private IWorkflowContext BoundContext { get; } = runContext.Bind(edgeData.SinkId);

    public FanInEdgeState CreateState() => new(this.EdgeData);

    public async ValueTask<IEnumerable<object?>> ChaseAsync(string sourceId, MessageEnvelope envelope, FanInEdgeState state, IStepTracer? tracer)
    {
        if (envelope.TargetId != null && this.EdgeData.SinkId != envelope.TargetId)
        {
            // This message is not for us.
            return [];
        }

        object message = envelope.Message;
        IEnumerable<object>? releasedMessages = state.ProcessMessage(sourceId, message);
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            return [];
        }

        Executor target = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, tracer)
                                               .ConfigureAwait(false);

        List<Task<object?>> messageTasks = [];

        foreach (var messageTask in releasedMessages)
        {
            if (target.CanHandle(messageTask.GetType()))
            {
                tracer?.TraceActivated(target.Id);
                messageTasks.Add(target.ExecuteAsync(messageTask, envelope.MessageType, this.BoundContext).AsTask());
            }
        }

        return await Task.WhenAll(messageTasks.ToArray()).ConfigureAwait(false);
    }
}
