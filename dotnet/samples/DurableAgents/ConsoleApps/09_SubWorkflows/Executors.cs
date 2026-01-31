// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SubWorkflows;

// ============================================
// Order Processing Models
// ============================================

/// <summary>
/// Represents an order being processed.
/// </summary>
internal sealed class OrderInfo
{
    public required string OrderId { get; set; }
    public decimal Amount { get; set; }
    public string? PaymentTransactionId { get; set; }
    public string? InventoryReservationId { get; set; }
    public string? TrackingNumber { get; set; }
    public string? Carrier { get; set; }
}

// ============================================
// Main Workflow Executors
// ============================================

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
        Console.WriteLine($"│   Inventory: {message.InventoryReservationId}");
        Console.WriteLine($"│   Shipping: {message.Carrier} - {message.TrackingNumber}");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult($"Order {message.OrderId} completed. Tracking: {message.TrackingNumber}");
    }
}

// ============================================
// Payment Sub-Workflow Executors
// ============================================

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

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ValidatePayment] Payment validated for ${message.Amount}");
        Console.ResetColor();

        return message;
    }
}

// ============================================
// Fraud Check Sub-Sub-Workflow Executors (Level 2 nesting)
// ============================================

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

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine("    [Payment/FraudCheck/AnalyzePatterns] ✓ Pattern analysis complete");
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

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        int riskScore = new Random().Next(1, 100);

        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine($"    [Payment/FraudCheck/CalculateRiskScore] ✓ Risk score: {riskScore}/100 (Low risk)");
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

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.PaymentTransactionId = $"TXN-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"  [Payment/ChargePayment] ✓ Payment processed: {message.PaymentTransactionId}");
        Console.ResetColor();

        return message;
    }
}

// ============================================
// Inventory Sub-Workflow Executors
// ============================================

/// <summary>
/// Checks inventory availability for an order.
/// </summary>
internal sealed class CheckInventory() : Executor<OrderInfo, OrderInfo>("CheckInventory")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"  [Inventory/CheckInventory] Checking inventory for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("  [Inventory/CheckInventory] ✓ Items available in stock");
        Console.ResetColor();

        return message;
    }
}

/// <summary>
/// Reserves inventory for an order.
/// </summary>
internal sealed class ReserveInventory() : Executor<OrderInfo, OrderInfo>("ReserveInventory")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"  [Inventory/ReserveInventory] Reserving items for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.InventoryReservationId = $"RES-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"  [Inventory/ReserveInventory] ✓ Reserved: {message.InventoryReservationId}");
        Console.ResetColor();

        return message;
    }
}

// ============================================
// Shipping Sub-Workflow Executors
// ============================================

/// <summary>
/// Selects a shipping carrier for an order.
/// </summary>
internal sealed class SelectCarrier() : Executor<OrderInfo, OrderInfo>("SelectCarrier")
{
    public override async ValueTask<OrderInfo> HandleAsync(OrderInfo message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/SelectCarrier] Selecting carrier for order '{message.OrderId}'...");
        Console.ResetColor();

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        message.Carrier = message.Amount > 50 ? "Express" : "Standard";

        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/SelectCarrier] ✓ Selected carrier: {message.Carrier}");
        Console.ResetColor();

        return message;
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

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.TrackingNumber = $"TRACK-{Guid.NewGuid().ToString("N")[..10].ToUpperInvariant()}";

        Console.ForegroundColor = ConsoleColor.Blue;
        Console.WriteLine($"  [Shipping/CreateShipment] ✓ Shipment created: {message.TrackingNumber}");
        Console.ResetColor();

        return message;
    }
}
