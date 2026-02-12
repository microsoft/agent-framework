// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace ConditionalEdgesFunctionApp;

/// <summary>
/// Represents an order with customer and payment details.
/// </summary>
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

/// <summary>
/// Represents a customer associated with an order.
/// </summary>
public sealed record Customer(int Id, string Name, bool IsBlocked);

/// <summary>
/// Parses the order ID and retrieves order details.
/// </summary>
internal sealed class OrderIdParser() : Executor<string, Order>("OrderIdParser")
{
    public override ValueTask<Order> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"[OrderIdParser] Parsing order ID: {message}");
        Order order = new(message, 100.0m);
        return ValueTask.FromResult(order);
    }
}

/// <summary>
/// Enriches the order with customer information.
/// Orders with IDs containing 'B' are associated with blocked customers.
/// </summary>
internal sealed class OrderEnrich() : Executor<Order, Order>("EnrichOrder")
{
    public override ValueTask<Order> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        message.Customer = GetCustomerForOrder(message.Id);
        Console.WriteLine($"[EnrichOrder] Customer: {message.Customer.Name}, IsBlocked: {message.Customer.IsBlocked}");
        return ValueTask.FromResult(message);
    }

    private static Customer GetCustomerForOrder(string orderId)
    {
        if (orderId.Contains('B'))
        {
            return new Customer(101, "George", true);
        }

        return new Customer(201, "Jerry", false);
    }
}

/// <summary>
/// Processes payment for valid (non-blocked) orders.
/// </summary>
internal sealed class PaymentProcessor() : Executor<Order, Order>("PaymentProcessor")
{
    public override ValueTask<Order> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        message.PaymentReferenceNumber = Guid.NewGuid().ToString()[..4];
        Console.WriteLine($"[PaymentProcessor] Payment processed for order {message.Id}. Reference: {message.PaymentReferenceNumber}");
        return ValueTask.FromResult(message);
    }
}

/// <summary>
/// Notifies the fraud team when a blocked customer places an order.
/// </summary>
internal sealed class NotifyFraud() : Executor<Order, string>("NotifyFraud")
{
    public override ValueTask<string> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        string result = $"Order {message.Id} flagged as fraudulent for customer {message.Customer?.Name}.";
        Console.WriteLine($"[NotifyFraud] {result}");
        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Defines condition functions for routing orders based on customer status.
/// </summary>
internal static class OrderRouteConditions
{
    /// <summary>
    /// Returns a condition that evaluates to true when the customer is blocked.
    /// </summary>
    internal static Func<Order?, bool> WhenBlocked() => order => order?.Customer?.IsBlocked == true;

    /// <summary>
    /// Returns a condition that evaluates to true when the customer is not blocked.
    /// </summary>
    internal static Func<Order?, bool> WhenNotBlocked() => order => order?.Customer?.IsBlocked == false;
}
