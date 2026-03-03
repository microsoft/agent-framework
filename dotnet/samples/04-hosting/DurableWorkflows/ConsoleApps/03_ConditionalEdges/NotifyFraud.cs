// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace ConditionalEdges;

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

public sealed record Customer(int Id, string Name, bool IsBlocked);

internal sealed class OrderIdParser() : Executor<string, Order>("OrderIdParser")
{
    public override async ValueTask<Order> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return GetOrder(message);
    }

    private static Order GetOrder(string id)
    {
        // Simulate fetching order details
        return new Order(id, 100.0m);
    }
}

internal sealed class OrderEnrich() : Executor<Order, Order>("EnrichOrder")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        message.Customer = GetCustomerForOrder(message.Id);
        return message;
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

internal sealed class PaymentProcesser() : Executor<Order, Order>("PaymentProcesser")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Call payment gateway.
        message.PaymentReferenceNumber = Guid.NewGuid().ToString().Substring(0, 4);
        return message;
    }
}

internal sealed class NotifyFraud() : Executor<Order, string>("NotifyFraud")
{
    public override async ValueTask<string> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Notify fraud team.
        return $"Order {message.Id} flagged as fraudulent for customer {message.Customer?.Name}.";
    }
}

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
