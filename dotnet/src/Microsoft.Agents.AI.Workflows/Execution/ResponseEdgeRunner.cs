// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class ResponseEdgeRunner(IRunnerContext runContext, string sinkId)
    : EdgeRunner<string>(runContext, sinkId)
{
    public static ResponseEdgeRunner ForPort(IRunnerContext runContext, RequestPort port)
    {
        Throw.IfNull(port);

        // The port is an request port, so we can use the port's ID as the sink ID.
        return new ResponseEdgeRunner(runContext, port.Id);
    }

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        Debug.Assert(envelope.IsExternal, "Input edges should only be chased from external input");

        using var activity = s_activitySource.StartActivity(ActivityNames.EdgeGroupProcess);
        activity?
            .SetTag(Tags.EdgeGroupType, nameof(ResponseEdgeRunner))
            .SetTag(Tags.MessageSourceId, envelope.SourceId)
            .SetTag(Tags.MessageTargetId, this.EdgeData);

        try
        {
            Executor target = await this.FindExecutorAsync(stepTracer).ConfigureAwait(false);
            if (target.CanHandle(envelope.MessageType))
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Delivered);
                return new DeliveryMapping(envelope, target);
            }

            activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTypeMismatch);
            return null;
        }
        catch (Exception) when (activity is not null)
        {
            activity.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Exception);
            throw;
        }
    }

    private async ValueTask<Executor> FindExecutorAsync(IStepTracer? tracer) => await this.RunContext.EnsureExecutorAsync(this.EdgeData, tracer).ConfigureAwait(false);
}
