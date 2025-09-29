// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Observability;

internal enum EdgeRunnerDeliveryStatus
{
    Delivered,
    DroppedTypeMismatch,
    DroppedTargetMismatch,
    DroppedConditionFalse,
    Exception,
    Buffered
}

internal static class EdgeRunnerDeliveryStatusExtensions
{
    public static string ToStringValue(this EdgeRunnerDeliveryStatus status)
    {
        return status switch
        {
            EdgeRunnerDeliveryStatus.Delivered => "delivered",
            EdgeRunnerDeliveryStatus.DroppedTypeMismatch => "dropped type mismatch",
            EdgeRunnerDeliveryStatus.DroppedTargetMismatch => "dropped target mismatch",
            EdgeRunnerDeliveryStatus.DroppedConditionFalse => "dropped condition false",
            EdgeRunnerDeliveryStatus.Exception => "exception",
            EdgeRunnerDeliveryStatus.Buffered => "buffered",
            _ => throw new System.NotImplementedException(),
        };
    }
}
