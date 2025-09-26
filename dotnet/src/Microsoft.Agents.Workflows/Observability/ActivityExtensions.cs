// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;

namespace Microsoft.Agents.Workflows.Observability;

internal static class ActivityExtensions
{
    /// <summary>
    /// Capture exception details in the activity.
    /// </summary>
    /// <param name="activity">The activity to capture exception details in.</param>
    /// <param name="exception">The exception to capture.</param>
    /// <remarks>
    /// This method adds standard error tags to the activity and logs an event with exception details.
    /// </remarks>
    internal static void CaptureException(this Activity? activity, Exception exception)
    {
        activity?.SetTag(Tags.ErrorType, exception.GetType().FullName)
            .AddException(exception)
            .SetStatus(ActivityStatusCode.Error, exception.Message);
    }

    internal static void SetEdgeRunnerDeliveryStatus(this Activity? activity, EdgeRunnerDeliveryStatus status)
    {
        var delivered = status == EdgeRunnerDeliveryStatus.Delivered;
        activity?
            .SetTag(Tags.EdgeGroupDelivered, delivered)
            .SetTag(Tags.EdgeGroupDeliveryStatus, status.ToStringValue());
    }
}