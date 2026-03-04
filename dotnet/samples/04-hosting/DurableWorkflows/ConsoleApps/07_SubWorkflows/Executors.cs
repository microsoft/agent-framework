// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SubWorkflows;

/// <summary>
/// Event emitted when the fraud check risk score is calculated.
/// </summary>
internal sealed class FraudRiskAssessedEvent(int riskScore) : WorkflowEvent($"Risk score: {riskScore}/100")
{
    public int RiskScore => riskScore;
}

/// <summary>
/// Represents an order being processed through the workflow.
/// </summary>
internal sealed class OrderInfo
{
    public required string OrderId { get; set; }

    public decimal Amount { get; set; }

    public string? PaymentTransactionId { get; set; }

    public string? TrackingNumber { get; set; }

    public string? Carrier { get; set; }
}

// Main workflow executors

/// <summary>
/// Entry point executor that receives the order ID and creates an OrderInfo object.
/// </summary>
internal sealed class OrderReceived() : Executor<string, OrderInfo>("OrderReceived")
{
    public override ValueTask<OrderInfo> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine($"[OrderReceived] Processing order '{message}'");
        Console.ResetColor();

        OrderInfo order = new()
        {
            OrderId = message,
            Amount = 99.99m // Simulated order amount
        };

        return ValueTask.FromResult(order);
    }
}

/// <summary>
/// Final executor that outputs the completed order summary.
/// </summary>
internal sealed class OrderCompleted() : Executor<OrderInfo, string>("OrderCompleted")
{
    public override ValueTask<string> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [OrderCompleted] Order '{message.OrderId}' successfully processed!");
        Console.WriteLine($"│   Payment: {message.PaymentTransactionId}");
        Console.WriteLine($"│   Shipping: {message.Carrier} - {message.TrackingNumber}");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult($"Order {message.OrderId} completed. Tracking: {message.TrackingNumber}");
    }
}

// Payment sub-workflow executors

/// <summary>
/// Validates payment information for an order.
/// </summary>
internal sealed class ValidatePayment() : Executor<OrderInfo, OrderInfo>("ValidatePayment")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ValidatePayment] Validating payment for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ValidatePayment] Payment validated for ${message.Amount}");
        Console.ResetColor();

        return message;
    }
}

/// <summary>
/// Charges the payment for an order.
/// </summary>
internal sealed class ChargePayment() : Executor<OrderInfo, OrderInfo>("ChargePayment")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ChargePayment] Charging ${message.Amount} for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        message.PaymentTransactionId = $"TXN-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ChargePayment] ✓ Payment processed: {message.PaymentTransactionId}");
        Console.ResetColor();

        return message;
    }
}

// FraudCheck sub-sub-workflow executors (nested inside Payment)

/// <summary>
/// Analyzes transaction patterns for potential fraud.
/// </summary>
internal sealed class AnalyzePatterns() : Executor<OrderInfo, OrderInfo>("AnalyzePatterns")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine($"    [Payment/FraudCheck/AnalyzePatterns] Analyzing patterns for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        // Store analysis results in shared state for the next executor in this sub-workflow
        int patternsFound = new Random().Next(0, 5);
        await context.QueueStateUpdateAsync("patternsFound", patternsFound, cancellationToken: cancellationToken);

        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine($"    [Payment/FraudCheck/AnalyzePatterns] ✓ Pattern analysis complete ({patternsFound} suspicious patterns)");
        Console.ResetColor();

        return message;
    }
}

/// <summary>
/// Calculates a risk score for the transaction.
/// </summary>
internal sealed class CalculateRiskScore() : Executor<OrderInfo, OrderInfo>("CalculateRiskScore")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine($"    [Payment/FraudCheck/CalculateRiskScore] Calculating risk score for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        // Read the pattern count from shared state (written by AnalyzePatterns)
        int patternsFound = await context.ReadStateAsync<int>("patternsFound", cancellationToken: cancellationToken);
        int riskScore = Math.Min(patternsFound * 20 + new Random().Next(1, 20), 100);

        // Emit a workflow event from within a nested sub-workflow
        await context.AddEventAsync(new FraudRiskAssessedEvent(riskScore), cancellationToken);

        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine($"    [Payment/FraudCheck/CalculateRiskScore] ✓ Risk score: {riskScore}/100 (based on {patternsFound} patterns)");
        Console.ResetColor();

        return message;
    }
}

// Shipping sub-workflow executors

/// <summary>
/// Selects a shipping carrier for an order.
/// </summary>
/// <remarks>
/// This executor uses <see cref="Executor{TInput}"/> (void return) combined with
/// <see cref="IWorkflowContext.SendMessageAsync"/> to forward the order to the next
/// connected executor (CreateShipment). This demonstrates explicit typed message passing
/// as an alternative to returning a value from the handler.
/// </remarks>
internal sealed class SelectCarrier() : Executor<OrderInfo>("SelectCarrier")
{
    public override async ValueTask HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/SelectCarrier] Selecting carrier for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        message.Carrier = message.Amount > 50 ? "Express" : "Standard";

        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/SelectCarrier] ✓ Selected carrier: {message.Carrier}");
        Console.ResetColor();

        // Use SendMessageAsync to forward the updated order to connected executors.
        // With a void-return executor, this is the mechanism for passing data downstream.
        await context.SendMessageAsync(message, cancellationToken: cancellationToken);
    }
}

/// <summary>
/// Creates shipment and generates tracking number.
/// </summary>
internal sealed class CreateShipment() : Executor<OrderInfo, OrderInfo>("CreateShipment")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/CreateShipment] Creating shipment for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        message.TrackingNumber = $"TRACK-{Guid.NewGuid().ToString("N")[..10].ToUpperInvariant()}";

        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/CreateShipment] ✓ Shipment created: {message.TrackingNumber}");
        Console.ResetColor();

        return message;
    }
}
