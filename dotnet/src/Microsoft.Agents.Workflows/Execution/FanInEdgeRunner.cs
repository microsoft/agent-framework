// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData)
{
    private IWorkflowContext BoundContext { get; } = runContext.Bind(edgeData.SinkId);

    public FanInEdgeState CreateState() => new(this.EdgeData);

    public ValueTask<IEnumerable<object?>> ChaseAsync(string sourceId, MessageEnvelope envelope, FanInEdgeState state, IStepTracer? tracer)
    {
        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            // This message is not for us.
            return new([]);
        }

        IEnumerable<MessageEnvelope>? releasedMessages = state.ProcessMessage(sourceId, envelope);
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            return new([]);
        }

        return this.ForwardReleasedMessagesAsync(releasedMessages, tracer);
    }

    private async ValueTask<IEnumerable<object?>> ForwardReleasedMessagesAsync(IEnumerable<MessageEnvelope> releasedMessages, IStepTracer? tracer)
    {
        Executor target = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, tracer)
                                               .ConfigureAwait(false);

        List<Task<object?>> messageTasks = [];

        foreach (MessageEnvelope releasedEnvelope in releasedMessages)
        {
            object message = releasedEnvelope.Message;
            Debug.Assert(message is PortableValue, "It should not be possible to get messages released without roundtripping them through" +
                "PortableValue via PortableMessageEnvelope.");

            PortableValue portable = message as PortableValue ?? new PortableValue(releasedEnvelope.MessageType, message);

            if (target.CanHandle(portable.TypeId))
            {
                tracer?.TraceActivated(target.Id);
                messageTasks.Add(target.ExecuteAsync(portable, releasedEnvelope.MessageType, this.BoundContext).AsTask());
            }
        }

        return await Task.WhenAll(messageTasks.ToArray()).ConfigureAwait(false);
    }
}
