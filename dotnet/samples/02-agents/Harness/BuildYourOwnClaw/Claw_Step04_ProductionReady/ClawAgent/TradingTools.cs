// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;

namespace ClawAgent;

/// <summary>
/// Sensitive claw tools that take real-world actions and therefore require human approval.
/// </summary>
internal static class TradingTools
{
    /// <summary>
    /// Places a simulated buy or sell order for a given symbol and quantity.
    /// </summary>
    [Description("Places a buy or sell order for a given symbol and quantity.")]
    public static string PlaceTrade(
        [Description("The stock ticker symbol to trade, e.g. MSFT.")] string symbol,
        [Description("Either 'buy' or 'sell'.")] string action,
        [Description("The number of shares to trade.")] int quantity)
    {
        var isBuy = action.Equals("buy", StringComparison.OrdinalIgnoreCase);
        var isSell = action.Equals("sell", StringComparison.OrdinalIgnoreCase);
        if (!isBuy && !isSell)
        {
            return $"Invalid action '{action}'. Use 'buy' or 'sell'.";
        }

        if (quantity <= 0)
        {
            return $"Invalid quantity '{quantity}'. Quantity must be a positive whole number of shares.";
        }

        var verb = isSell ? "Sold" : "Bought";
        var confirmation = $"TRADE-{Guid.NewGuid().ToString("N")[..8].ToUpperInvariant()}";
        return $"{verb} {quantity} share(s) of {symbol.ToUpperInvariant()}. Confirmation: {confirmation}.";
    }

    /// <summary>
    /// Creates an approval-required AI function for placing trades.
    /// </summary>
    public static AIFunction CreatePlaceTradeTool() =>
        new ApprovalRequiredAIFunction(AIFunctionFactory.Create(PlaceTrade, "place_trade"));
}
