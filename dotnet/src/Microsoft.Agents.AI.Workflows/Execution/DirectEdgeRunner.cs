// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class DirectEdgeRunner(IRunnerContext runContext, DirectEdgeData edgeData) :
    EdgeRunner<DirectEdgeData>(runContext, edgeData)
{
    private async ValueTask<Executor> FindRouterAsync(IStepTracer? tracer) => await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, tracer)
                                    .ConfigureAwait(false);

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        using var activity = s_activitySource.StartActivity(ActivityNames.EdgeGroupProcess);
        activity?
            .SetTag(Tags.EdgeGroupType, nameof(DirectEdgeRunner))
            .SetTag(Tags.MessageSourceId, this.EdgeData.SourceId)
            .SetTag(Tags.MessageTargetId, this.EdgeData.SinkId);

        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTargetMismatch);
            return null;
        }

        object message = envelope.Message;
        try
        {
            if (this.EdgeData.Condition is not null && !this.EdgeData.Condition(message))
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedConditionFalse);
                return null;
            }

            Executor target = await this.FindRouterAsync(stepTracer).ConfigureAwait(false);
            if (target.CanHandle(envelope.MessageType))
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Delivered);
                return new DeliveryMapping(envelope, target);
            }
        }
        catch (Exception) when (activity is not null)
        {
            activity.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Exception);
            throw;
        }

        activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTypeMismatch);
        return null;
    }
}
