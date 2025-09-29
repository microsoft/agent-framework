// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using OpenTelemetry.Context.Propagation;

namespace Microsoft.Agents.AI.Workflows.Observability;

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

    /// <summary>
    /// Executor processing spans are not nested, they are siblings.
    /// We use links to represent the causal relationship between them.
    /// </summary>
    internal static void CreateSourceLinks(this Activity? activity, IReadOnlyDictionary<string, string>? traceContext)
    {
        if (activity is null || traceContext is null)
        {
            return;
        }

        // Extract the propagation context from the dictionary
        var propagationContext = Propagators.DefaultTextMapPropagator.Extract(
            default,
            traceContext,
            (carrier, key) => carrier.TryGetValue(key, out var value) ? [value] : Array.Empty<string>());

        // Create a link to the source activity
        activity.AddLink(new ActivityLink(propagationContext.ActivityContext));
    }
}
