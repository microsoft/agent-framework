// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowMcpTool;

internal sealed class TranslateText() : Executor<string, TranslationResult>("TranslateText")
{
    public override ValueTask<TranslationResult> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"[Activity] TranslateText: '{message}'");
        return ValueTask.FromResult(new TranslationResult(message, message.ToUpperInvariant()));
    }
}

internal sealed class FormatOutput() : Executor<TranslationResult, string>("FormatOutput")
{
    public override ValueTask<string> HandleAsync(
        TranslationResult message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine("[Activity] FormatOutput: Formatting result");
        return ValueTask.FromResult($"Original: {message.Original} => Translated: {message.Translated}");
    }
}

internal sealed class LookupOrder() : Executor<string, OrderInfo>("LookupOrder")
{
    public override ValueTask<OrderInfo> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"[Activity] LookupOrder: '{message}'");
        return ValueTask.FromResult(new OrderInfo(message, "Alice Johnson", "Wireless Headphones", Quantity: 2, UnitPrice: 49.99m));
    }
}

internal sealed class EnrichOrder() : Executor<OrderInfo, OrderSummary>("EnrichOrder")
{
    public override ValueTask<OrderSummary> HandleAsync(
        OrderInfo message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"[Activity] EnrichOrder: '{message.OrderId}'");
        return ValueTask.FromResult(new OrderSummary(message, TotalPrice: message.Quantity * message.UnitPrice, Status: "Confirmed"));
    }
}

internal sealed record TranslationResult(string Original, string Translated);

internal sealed record OrderInfo(string OrderId, string CustomerName, string Product, int Quantity, decimal UnitPrice);

internal sealed record OrderSummary(OrderInfo Order, decimal TotalPrice, string Status);
