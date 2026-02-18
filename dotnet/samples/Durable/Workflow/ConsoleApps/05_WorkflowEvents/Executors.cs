// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowEvents;

// ═══════════════════════════════════════════════════════════════════════════════
// Custom event types - callers observe these via WatchStreamAsync
// ═══════════════════════════════════════════════════════════════════════════════

internal sealed class OrderLookupStartedEvent(string orderId) : WorkflowEvent(orderId)
{
    public string OrderId { get; } = orderId;
}

internal sealed class OrderFoundEvent(string customerName) : WorkflowEvent(customerName)
{
    public string CustomerName { get; } = customerName;
}

internal sealed class CancellationProgressEvent(int percentComplete, string status) : WorkflowEvent(status)
{
    public int PercentComplete { get; } = percentComplete;
    public string Status { get; } = status;
}

internal sealed class OrderCancelledEvent() : WorkflowEvent("Order cancelled");

internal sealed class EmailSentEvent(string email) : WorkflowEvent(email)
{
    public string Email { get; } = email;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Domain models
// ═══════════════════════════════════════════════════════════════════════════════

internal sealed record Order(string Id, DateTime OrderDate, bool IsCancelled, string? CancelReason, Customer Customer);

internal sealed record Customer(string Name, string Email);

// ═══════════════════════════════════════════════════════════════════════════════
// Executors - emit events via AddEventAsync and YieldOutputAsync
// ═══════════════════════════════════════════════════════════════════════════════

/// <summary>
/// Looks up an order by ID, emitting progress events.
/// </summary>
internal sealed class OrderLookup() : Executor<string, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await context.AddEventAsync(new OrderLookupStartedEvent(message), cancellationToken);

        // Simulate database lookup
        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Order order = new(
            Id: message,
            OrderDate: DateTime.UtcNow.AddDays(-1),
            IsCancelled: false,
            CancelReason: "Customer requested cancellation",
            Customer: new Customer(Name: "Jerry", Email: "jerry@example.com"));

        await context.AddEventAsync(new OrderFoundEvent(order.Customer.Name), cancellationToken);

        // YieldOutputAsync emits a WorkflowOutputEvent observable via streaming
        await context.YieldOutputAsync(order, cancellationToken);

        return order;
    }
}

/// <summary>
/// Cancels an order, emitting progress events during the multi-step process.
/// </summary>
internal sealed class OrderCancel() : Executor<Order, Order>("OrderCancel")
{
    public override async ValueTask<Order> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await context.AddEventAsync(new CancellationProgressEvent(0, "Starting cancellation"), cancellationToken);

        // Simulate a multi-step cancellation process
        await Task.Delay(TimeSpan.FromMilliseconds(500), cancellationToken);
        await context.AddEventAsync(new CancellationProgressEvent(33, "Contacting payment provider"), cancellationToken);

        await Task.Delay(TimeSpan.FromMilliseconds(500), cancellationToken);
        await context.AddEventAsync(new CancellationProgressEvent(66, "Processing refund"), cancellationToken);

        await Task.Delay(TimeSpan.FromMilliseconds(500), cancellationToken);

        Order cancelledOrder = message with { IsCancelled = true };
        await context.AddEventAsync(new CancellationProgressEvent(100, "Complete"), cancellationToken);
        await context.AddEventAsync(new OrderCancelledEvent(), cancellationToken);

        await context.YieldOutputAsync(cancelledOrder, cancellationToken);

        return cancelledOrder;
    }
}

/// <summary>
/// Sends a cancellation confirmation email, emitting an event on completion.
/// </summary>
internal sealed class SendEmail() : Executor<Order, string>("SendEmail")
{
    public override async ValueTask<string> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // Simulate sending email
        await Task.Delay(TimeSpan.FromMilliseconds(500), cancellationToken);

        string result = $"Cancellation email sent for order {message.Id} to {message.Customer.Email}.";

        await context.AddEventAsync(new EmailSentEvent(message.Customer.Email), cancellationToken);

        await context.YieldOutputAsync(result, cancellationToken);

        return result;
    }
}
