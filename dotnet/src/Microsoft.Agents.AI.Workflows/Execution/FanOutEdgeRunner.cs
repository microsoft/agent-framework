// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class FanOutEdgeRunner(IRunnerContext runContext, FanOutEdgeData edgeData) :
    EdgeRunner<FanOutEdgeData>(runContext, edgeData)
{
    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        using var activity = s_activitySource.StartActivity(ActivityNames.EdgeGroupProcess);
        activity?
            .SetTag(Tags.EdgeGroupType, nameof(FanOutEdgeRunner))
            .SetTag(Tags.MessageSourceId, this.EdgeData.SourceId);

        object message = envelope.Message;

        try
        {
            IEnumerable<string> targetIds =
                this.EdgeData.EdgeAssigner is null
                    ? this.EdgeData.SinkIds
                    : this.EdgeData.EdgeAssigner(message, this.EdgeData.SinkIds.Count)
                                .Select(i => this.EdgeData.SinkIds[i]);

            Executor[] result = await Task.WhenAll(targetIds.Where(IsValidTarget)
                                                            .Select(tid => this.RunContext.EnsureExecutorAsync(tid, stepTracer)
                                                            .AsTask()))
                                        .ConfigureAwait(false);

            if (result.Length == 0)
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTargetMismatch);
                return null;
            }

            IEnumerable<Executor> validTargets = result.Where(t => t.CanHandle(envelope.MessageType));

            if (!validTargets.Any())
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTypeMismatch);
                return null;
            }

            activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Delivered);

            return new DeliveryMapping(envelope, validTargets);
        }
        catch (Exception) when (activity is not null)
        {
            activity.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Exception);
            throw;
        }

        bool IsValidTarget(string targetId)
        {
            return envelope.TargetId is null || targetId == envelope.TargetId;
        }
    }
}
