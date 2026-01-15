// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Represents the details of a customer order.
/// </summary>
public sealed class OrderDetails
{
    public int OrderId { get; set; }

    public string CustomerName { get; set; } = string.Empty;

    public string CustomerEmail { get; set; } = string.Empty;

    public List<OrderItem> Items { get; set; } = [];

    public decimal TotalAmount { get; set; }

    public OrderStatus Status { get; set; }

    public DateTime OrderDate { get; set; }

    public DateTime? EstimatedDelivery { get; set; }
}

/// <summary>
/// Represents an item in an order.
/// </summary>
public sealed class OrderItem
{
    public string ProductName { get; set; } = string.Empty;

    public int Quantity { get; set; }

    public decimal UnitPrice { get; set; }

    public decimal Total => this.Quantity * this.UnitPrice;
}

/// <summary>
/// Represents the status of an order.
/// </summary>
public enum OrderStatus
{
    Pending,
    Processing,
    Shipped,
    Delivered,
    Cancelled
}

/// <summary>
/// Executor that looks up order details by order ID.
/// Input: int (orderId)
/// Output: OrderDetails
/// </summary>
internal sealed class OrderLookupExecutor() : Executor<int, OrderDetails>("OrderLookupExecutor")
{
    // Simulated order database
    private static readonly Dictionary<int, OrderDetails> s_orders = new()
    {
        [1001] = new OrderDetails
        {
            OrderId = 1001,
            CustomerName = "Alice Johnson",
            CustomerEmail = "alice@example.com",
            Items =
            [
                new OrderItem { ProductName = "Wireless Headphones", Quantity = 1, UnitPrice = 79.99m },
                new OrderItem { ProductName = "Phone Case", Quantity = 2, UnitPrice = 15.99m }
            ],
            TotalAmount = 111.97m,
            Status = OrderStatus.Shipped,
            OrderDate = DateTime.UtcNow.AddDays(-3),
            EstimatedDelivery = DateTime.UtcNow.AddDays(2)
        },
        [1002] = new OrderDetails
        {
            OrderId = 1002,
            CustomerName = "Bob Smith",
            CustomerEmail = "bob@example.com",
            Items =
            [
                new OrderItem { ProductName = "Laptop Stand", Quantity = 1, UnitPrice = 49.99m }
            ],
            TotalAmount = 49.99m,
            Status = OrderStatus.Processing,
            OrderDate = DateTime.UtcNow.AddDays(-1),
            EstimatedDelivery = DateTime.UtcNow.AddDays(5)
        },
        [1003] = new OrderDetails
        {
            OrderId = 1003,
            CustomerName = "Carol Davis",
            CustomerEmail = "carol@example.com",
            Items =
            [
                new OrderItem { ProductName = "USB-C Hub", Quantity = 1, UnitPrice = 35.00m },
                new OrderItem { ProductName = "HDMI Cable", Quantity = 3, UnitPrice = 12.99m },
                new OrderItem { ProductName = "Webcam", Quantity = 1, UnitPrice = 89.99m }
            ],
            TotalAmount = 163.96m,
            Status = OrderStatus.Delivered,
            OrderDate = DateTime.UtcNow.AddDays(-7),
            EstimatedDelivery = null
        }
    };

    public override ValueTask<OrderDetails> HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (s_orders.TryGetValue(message, out OrderDetails? order))
        {
            return ValueTask.FromResult(order);
        }

        // Return a "not found" order
        return ValueTask.FromResult(new OrderDetails
        {
            OrderId = message,
            CustomerName = "Unknown",
            Status = OrderStatus.Cancelled,
            OrderDate = DateTime.UtcNow
        });
    }
}

/// <summary>
/// Executor that generates a human-readable summary from order details.
/// Input: OrderDetails
/// Output: string
/// </summary>
internal sealed class OrderSummaryExecutor() : Executor<OrderDetails, string>("OrderSummaryExecutor")
{
    public override ValueTask<string> HandleAsync(OrderDetails message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (message.CustomerName == "Unknown")
        {
            return ValueTask.FromResult($"❌ Order #{message.OrderId} was not found in our system.");
        }

        string statusEmoji = message.Status switch
        {
            OrderStatus.Pending => "⏳",
            OrderStatus.Processing => "🔄",
            OrderStatus.Shipped => "📦",
            OrderStatus.Delivered => "✅",
            OrderStatus.Cancelled => "❌",
            _ => "❓"
        };

        string itemsList = string.Join("\n", message.Items.Select(i =>
            $"  • {i.ProductName} (x{i.Quantity}) - ${i.Total:F2}"));

        string deliveryInfo = message.Status == OrderStatus.Delivered
            ? "Delivered!"
            : message.EstimatedDelivery.HasValue
                ? $"Expected: {message.EstimatedDelivery.Value:MMM dd, yyyy}"
                : "Calculating...";

        string summary = $"""
            ═══════════════════════════════════════
            📋 ORDER SUMMARY - #{message.OrderId}
            ═══════════════════════════════════════
            
            👤 Customer: {message.CustomerName}
            📧 Email: {message.CustomerEmail}
            📅 Order Date: {message.OrderDate:MMM dd, yyyy}
            
            {statusEmoji} Status: {message.Status}
            🚚 Delivery: {deliveryInfo}
            
            ─────────────────────────────────────────
            📦 ITEMS:
            {itemsList}
            ─────────────────────────────────────────
            
            💰 TOTAL: ${message.TotalAmount:F2}
            ═══════════════════════════════════════
            """;

        return ValueTask.FromResult(summary);
    }
}

/// <summary>
/// Executor that parses a string input to extract an order ID.
/// Input: string (e.g., "Check order 1001" or just "1001")
/// Output: int (orderId)
/// </summary>
internal sealed class OrderIdParserExecutor() : Executor<string, int>("OrderIdParserExecutor")
{
    public override ValueTask<int> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Try to extract order ID from the message
        // Handles formats like: "1001", "order 1001", "Check order #1001", etc.
        string cleanedInput = message
            .Replace("order", "", StringComparison.OrdinalIgnoreCase)
            .Replace("#", "")
            .Trim();

        // Find the first number in the string
        string numberStr = new(cleanedInput.Where(char.IsDigit).ToArray());

        if (int.TryParse(numberStr, out int orderId))
        {
            return ValueTask.FromResult(orderId);
        }

        // Default to an invalid order ID if parsing fails
        return ValueTask.FromResult(-1);
    }
}
