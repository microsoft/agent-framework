// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SequentialWorkflow;

/// <summary>
/// Represents a request to cancel an order.
/// </summary>
/// <param name="OrderId">The ID of the order to cancel.</param>
/// <param name="Reason">The reason for cancellation.</param>
internal sealed record OrderCancelRequest(string OrderId, string Reason);

/// <summary>
/// Looks up an order by its ID and return an Order object.
/// </summary>
internal sealed class OrderLookup() : Executor<OrderCancelRequest, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(
        OrderCancelRequest message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] OrderLookup: Starting lookup for order '{message.OrderId}'");
        Console.WriteLine($"│ [Activity] OrderLookup: Cancellation reason: '{message.Reason}'");
        Console.ResetColor();

        // Simulate database lookup with delay
        await Task.Delay(TimeSpan.FromMicroseconds(100), cancellationToken);

        Order order = new(
            Id: message.OrderId,
            OrderDate: DateTime.UtcNow.AddDays(-1),
            IsCancelled: false,
            CancelReason: message.Reason,
            Customer: new Customer(Name: "Jerry", Email: "jerry@example.com"));

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"│ [Activity] OrderLookup: Found order '{message.OrderId}' for customer '{order.Customer.Name}'");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return order;
    }
}

/// <summary>
/// Cancels an order.
/// </summary>
internal sealed class OrderCancel() : Executor<Order, Order>("OrderCancel")
{
    public override async ValueTask<Order> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // Log that this activity is executing (not replaying)
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] OrderCancel: Starting cancellation for order '{message.Id}'");
        Console.ResetColor();

        // Simulate a slow cancellation process (e.g., calling external payment system)
        for (int i = 1; i <= 3; i++)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);
            Console.ForegroundColor = ConsoleColor.DarkYellow;
            Console.WriteLine("│ [Activity] OrderCancel: Processing...");
            Console.ResetColor();
        }

        Order cancelledOrder = message with { IsCancelled = true };

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"│ [Activity] OrderCancel: ✓ Order '{cancelledOrder.Id}' has been cancelled");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return cancelledOrder;
    }
}

/// <summary>
/// Sends a cancellation confirmation email to the customer.
/// </summary>
internal sealed class SendEmail() : Executor<Order, string>("SendEmail")
{
    public override ValueTask<string> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] SendEmail: Sending email to '{message.Customer.Email}'...");
        Console.ResetColor();

        string result = $"Cancellation email sent for order {message.Id} to {message.Customer.Email}.";

        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("│ [Activity] SendEmail: ✓ Email sent successfully!");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult(result);
    }
}

internal sealed record Order(string Id, DateTime OrderDate, bool IsCancelled, string? CancelReason, Customer Customer);

internal sealed record Customer(string Name, string Email);
