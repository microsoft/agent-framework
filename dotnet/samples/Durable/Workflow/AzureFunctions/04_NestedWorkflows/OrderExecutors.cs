// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace NestedWorkflowsFunctionApp;

// ============================================
// Order Processing Models
// ============================================

/// <summary>
/// Represents an order being processed through the workflow.
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
        Console.WriteLine($"[OrderReceived] Processing order '{message}'");

        OrderInfo order = new()
        {
            OrderId = message,
            Amount = 99.99m
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
        Console.WriteLine($"[OrderCompleted] Order '{message.OrderId}' processed. Payment: {message.PaymentTransactionId}, Inventory: {message.InventoryReservationId}, Shipping: {message.Carrier} - {message.TrackingNumber}");

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
        Console.WriteLine($"[Payment/ValidatePayment] Validating payment for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.WriteLine($"[Payment/ValidatePayment] Payment validated for ${message.Amount}");

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
        Console.WriteLine($"[Payment/FraudCheck/AnalyzePatterns] Analyzing patterns for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.WriteLine("[Payment/FraudCheck/AnalyzePatterns] Pattern analysis complete");

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
        Console.WriteLine($"[Payment/FraudCheck/CalculateRiskScore] Calculating risk score for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        int riskScore = new Random().Next(1, 100);

        Console.WriteLine($"[Payment/FraudCheck/CalculateRiskScore] Risk score: {riskScore}/100 (Low risk)");

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
        Console.WriteLine($"[Payment/ChargePayment] Charging ${message.Amount} for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.PaymentTransactionId = $"TXN-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";

        Console.WriteLine($"[Payment/ChargePayment] Payment processed: {message.PaymentTransactionId}");

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
        Console.WriteLine($"[Inventory/CheckInventory] Checking inventory for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        Console.WriteLine("[Inventory/CheckInventory] Items available in stock");

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
        Console.WriteLine($"[Inventory/ReserveInventory] Reserving items for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.InventoryReservationId = $"RES-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";

        Console.WriteLine($"[Inventory/ReserveInventory] Reserved: {message.InventoryReservationId}");

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
        Console.WriteLine($"[Shipping/SelectCarrier] Selecting carrier for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);

        message.Carrier = message.Amount > 50 ? "Express" : "Standard";

        Console.WriteLine($"[Shipping/SelectCarrier] Selected carrier: {message.Carrier}");

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
        Console.WriteLine($"[Shipping/CreateShipment] Creating shipment for order '{message.OrderId}'");

        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        message.TrackingNumber = $"TRACK-{Guid.NewGuid().ToString("N")[..10].ToUpperInvariant()}";

        Console.WriteLine($"[Shipping/CreateShipment] Shipment created: {message.TrackingNumber}");

        return message;
    }
}
