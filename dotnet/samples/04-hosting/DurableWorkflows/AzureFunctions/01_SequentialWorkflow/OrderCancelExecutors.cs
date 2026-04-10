// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SequentialWorkflow;

/// <summary>
/// Looks up an order by its ID and return an Order object.
/// </summary>
internal sealed class OrderLookup() : Executor<string, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] OrderLookup: Starting lookup for order '{message}'");
        Console.ResetColor();

        // Simulate database lookup with delay
        await Task.Delay(TimeSpan.FromMicroseconds(100), cancellationToken);

        Order order = new(
            Id: message,
            OrderDate: DateTime.UtcNow.AddDays(-1),
            IsCancelled: false,
            Customer: new Customer(Name: "Jerry", Email: "jerry@example.com"));

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"│ [Activity] OrderLookup: Found order '{message}' for customer '{order.Customer.Name}'");
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

internal sealed record Order(string Id, DateTime OrderDate, bool IsCancelled, Customer Customer);

internal sealed record Customer(string Name, string Email);

/// <summary>
/// Represents a batch cancellation request with multiple order IDs and a reason.
/// This demonstrates using a complex typed object as workflow input.
/// </summary>
#pragma warning disable CA1812 // Instantiated via JSON deserialization at runtime
internal sealed record BatchCancelRequest(string[] OrderIds, string Reason, bool NotifyCustomers);
#pragma warning restore CA1812

/// <summary>
/// Represents the result of processing a batch cancellation.
/// </summary>
internal sealed record BatchCancelResult(int TotalOrders, int CancelledCount, string Reason);

/// <summary>
/// Generates a status report for an order.
/// </summary>
internal sealed class StatusReport() : Executor<Order, string>("StatusReport")
{
    public override ValueTask<string> HandleAsync(
        Order message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] StatusReport: Generating report for order '{message.Id}'");
        Console.ResetColor();

        string status = message.IsCancelled ? "Cancelled" : "Active";
        string result = $"Order {message.Id} for {message.Customer.Name}: Status={status}, Date={message.OrderDate:yyyy-MM-dd}";

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"│ [Activity] StatusReport: ✓ {result}");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Processes a batch cancellation request. Accepts a complex <see cref="BatchCancelRequest"/> object
/// as input, demonstrating how workflows can receive structured JSON input.
/// </summary>
internal sealed class BatchCancelProcessor() : Executor<BatchCancelRequest, BatchCancelResult>("BatchCancelProcessor")
{
    public override async ValueTask<BatchCancelResult> HandleAsync(
        BatchCancelRequest message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] BatchCancelProcessor: Processing {message.OrderIds.Length} orders");
        Console.WriteLine($"│ [Activity] BatchCancelProcessor: Reason: {message.Reason}");
        Console.WriteLine($"│ [Activity] BatchCancelProcessor: Notify customers: {message.NotifyCustomers}");
        Console.ResetColor();

        // Simulate processing each order
        int cancelledCount = 0;
        foreach (string orderId in message.OrderIds)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);
            cancelledCount++;
            Console.ForegroundColor = ConsoleColor.DarkYellow;
            Console.WriteLine($"│ [Activity] BatchCancelProcessor: ✓ Cancelled order '{orderId}'");
            Console.ResetColor();
        }

        BatchCancelResult result = new(message.OrderIds.Length, cancelledCount, message.Reason);

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"│ [Activity] BatchCancelProcessor: ✓ Batch complete: {cancelledCount}/{message.OrderIds.Length} cancelled");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return result;
    }
}

/// <summary>
/// Generates a summary of the batch cancellation.
/// </summary>
internal sealed class BatchCancelSummary() : Executor<BatchCancelResult, string>("BatchCancelSummary")
{
    public override ValueTask<string> HandleAsync(
        BatchCancelResult message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine("│ [Activity] BatchCancelSummary: Generating summary");
        Console.ResetColor();

        string result = $"Batch cancellation complete: {message.CancelledCount}/{message.TotalOrders} orders cancelled. Reason: {message.Reason}";

        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine($"│ [Activity] BatchCancelSummary: ✓ {result}");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult(result);
    }
}
