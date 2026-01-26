// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Event emitted when an order is found.
/// </summary>
public sealed class OrderFoundEvent(Order order) : WorkflowEvent($"Found order {order.Id} for {order.Customer.Name}")
{
    public Order Order { get; } = order;
}
