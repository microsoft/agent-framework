// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Event emitted when an order lookup starts.
/// </summary>
public sealed class OrderLookupStartedEvent(string orderId) : WorkflowEvent($"Looking up order {orderId}")
{
    public string OrderId { get; } = orderId;
}
