// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Event emitted when an order is successfully cancelled.
/// </summary>
public sealed class OrderCancelledEvent(string orderId) : WorkflowEvent($"Order {orderId} has been cancelled")
{
    public string OrderId { get; } = orderId;
}
