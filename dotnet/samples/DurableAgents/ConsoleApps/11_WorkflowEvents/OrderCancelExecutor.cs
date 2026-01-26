// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use IWorkflowContext methods in your executors:
// - AddEventAsync: Emit custom events that can be observed by the workflow caller
// - YieldOutputAsync: Stream intermediate outputs during execution
//
// These features enable rich observability and control over workflow execution.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

#region Domain Models

/// <summary>
/// Represents an order in the system.
/// </summary>
public sealed class Order
{
    public required string Id { get; set; }
    public DateTime OrderDate { get; set; }
    public bool IsCancelled { get; set; }
    public required Customer Customer { get; set; }
}

/// <summary>
/// Represents a customer associated with an order.
/// </summary>
public sealed class Customer
{
    public string Name { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
}

#endregion
#region Custom Workflow Events

#endregion

#region Executors

/// <summary>
/// Looks up an order by its ID. Demonstrates AddEventAsync for custom events.
/// </summary>
internal sealed class OrderLookup() : Executor<string, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await context.AddEventAsync(new OrderLookupStartedEvent(message), cancellationToken);
        await Task.Delay(500, cancellationToken);

        Order order = new()
        {
            Id = message,
            OrderDate = DateTime.UtcNow.AddDays(-3),
            IsCancelled = false,
            Customer = new Customer { Name = "Jerry", Email = "jerry@example.com" }
        };

        await context.AddEventAsync(new OrderFoundEvent(order), cancellationToken);
        return order;
    }
}

/// <summary>
/// Cancels an order with progress reporting.
/// Demonstrates AddEventAsync for progress events and YieldOutputAsync for streaming outputs.
/// </summary>
internal sealed class OrderCancel() : Executor<Order, Order>("OrderCancel")
{
    public override async ValueTask<Order> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // Simulate cancellation steps with progress events
        string[] steps = ["Validating", "Processing refund", "Finalizing"];
        for (int i = 0; i < steps.Length; i++)
        {
            await Task.Delay(500, cancellationToken);
            int percent = (i + 1) * 33;

            // Emit progress event (callers can observe this in real-time)
            await context.AddEventAsync(new CancellationProgressEvent(message.Id, percent, steps[i]), cancellationToken);

            // YieldOutputAsync streams intermediate results matching the executor's return type
            await context.YieldOutputAsync(message, cancellationToken);
        }

        message.IsCancelled = true;
        await context.AddEventAsync(new OrderCancelledEvent(message.Id), cancellationToken);
        return message;
    }
}

/// <summary>
/// Sends a cancellation confirmation email. Demonstrates AddEventAsync for completion events.
/// </summary>
internal sealed class SendEmail() : Executor<Order, string>("SendEmail")
{
    public override async ValueTask<string> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(500, cancellationToken);

        string email = message.Customer.Email;
        await context.AddEventAsync(new EmailSentEvent(email, $"Order {message.Id} Cancelled"), cancellationToken);
        return $"Email sent to {email}";
    }
}

#endregion
