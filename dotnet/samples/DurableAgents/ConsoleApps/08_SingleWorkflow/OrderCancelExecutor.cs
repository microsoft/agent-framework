// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Represents an order in the system.
/// </summary>
internal sealed class Order
{
    public required string Id { get; set; }
    public DateTime OrderDate { get; set; }
    public bool IsCancelled { get; set; }
    public required Customer Customer { get; set; }
}

/// <summary>
/// Represents a customer associated with an order.
/// </summary>
internal sealed class Customer
{
    public string Name { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
}

/// <summary>
/// Looks up an order by its ID.
/// This activity simulates a database lookup with a 2 second delay.
/// </summary>
internal sealed class OrderLookup() : Executor<string, Order>("OrderLookup")
{
    public override async ValueTask<Order> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Log that this activity is executing (not replaying)
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] OrderLookup: Starting lookup for order '{message}'");
        Console.ResetColor();

        // Simulate database lookup with delay
        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        Order order = new()
        {
            Id = message,
            OrderDate = DateTime.UtcNow.AddDays(-1),
            IsCancelled = false,
            Customer = new Customer { Name = "Jerry", Email = "jerry@example.com" }
        };

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"│ [Activity] OrderLookup: Found order '{message}' for customer '{order.Customer.Name}'");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return order;
    }
}

/// <summary>
/// Cancels an order.
/// This activity simulates a slow cancellation process with a 5 second delay.
/// Try pressing Ctrl+C during this activity to see durability in action!
/// </summary>
internal sealed class OrderCancel() : Executor<Order, Order>("OrderCancel")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Log that this activity is executing (not replaying)
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] OrderCancel: Starting cancellation for order '{message.Id}'");
        Console.WriteLine("│ [Activity] OrderCancel: ⚠️  This takes 5 seconds - try Ctrl+C!");
        Console.ResetColor();

        // Simulate a slow cancellation process (e.g., calling external payment system)
        // This is where you can kill the process to test durability
        for (int i = 1; i <= 10; i++)
        {
            await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
            Console.ForegroundColor = ConsoleColor.DarkYellow;
            Console.WriteLine($"│ [Activity] OrderCancel: Processing... {i}/10 seconds");
            Console.ResetColor();
        }

        // Mark the order as cancelled
        message.IsCancelled = true;

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"│ [Activity] OrderCancel: ✓ Order '{message.Id}' has been cancelled");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return message;
    }
}

/// <summary>
/// Sends a cancellation confirmation email to the customer.
/// This activity simulates sending an email with a 1 second delay.
/// </summary>
internal sealed class SendEmail() : Executor<Order, string>("SendEmail")
{
    public override async ValueTask<string> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Log that this activity is executing (not replaying)
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Activity] SendEmail: Sending email to '{message.Customer.Email}'...");
        Console.ResetColor();

        // Simulate email sending delay
        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        string result = $"Cancellation email sent to {message.Customer.Email} for order {message.Id}.";

        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("│ [Activity] SendEmail: ✓ Email sent successfully!");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return result;
    }
}
