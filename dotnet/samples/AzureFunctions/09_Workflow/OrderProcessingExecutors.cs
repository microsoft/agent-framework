// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Parses an Order ID from a string input and returns an Order object populated.
/// </summary>
internal sealed class OrderLookupExecutor() : Executor<string, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Populate Order information from OrderId.
        return new Order(message, 100.0m);
    }
}

/// <summary>
/// Enriches an Order object with additional information.
/// </summary>
internal sealed class OrderEnricherExecutor() : Executor<Order, Order>("EnrichOrder")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (message.Customer is null)
        {
            // populate customer information for the order from database.
            message.Customer = new Customer(1, "Jerry");
        }

        return message;
    }
}

internal sealed class PaymentProcessorExecutor() : Executor<Order, Order>("ProcessPayment")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        message.PaymentReferenceNumber = Guid.NewGuid().ToString()[^4..];

        return message;
    }
}

internal sealed class Order
{
    public Order(string id, decimal amount)
    {
        this.Id = id;
        this.Amount = amount;
    }
    public string Id { get; }
    public decimal Amount { get; }
    public Customer? Customer { get; set; }
    public string? PaymentReferenceNumber { get; set; }
}

public sealed record Customer(int Id, string Name);
