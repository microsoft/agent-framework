// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Event emitted to report cancellation progress.
/// </summary>
public sealed class CancellationProgressEvent(string orderId, int percentComplete, string status)
    : WorkflowEvent($"Cancellation {percentComplete}%: {status}")
{
    public string OrderId { get; } = orderId;
    public int PercentComplete { get; } = percentComplete;
    public string Status { get; } = status;
}
