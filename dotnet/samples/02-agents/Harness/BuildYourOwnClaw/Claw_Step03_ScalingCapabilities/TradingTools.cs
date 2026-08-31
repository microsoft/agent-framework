// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;

namespace ClawSample;

/// <summary>
/// Sensitive "claw" tools that take real-world actions and therefore require human approval.
/// </summary>
/// <remarks>
/// These tools only simulate their effects (no orders are placed, no email is sent). They exist
/// to demonstrate how the harness gates risky actions behind an approval prompt.
/// </remarks>
internal static class TradingTools
{
    // <place_trade>
    /// <summary>
    /// Places a (simulated) buy or sell order for a given symbol and quantity.
    /// </summary>
    /// <param name="symbol">The stock ticker symbol to trade, e.g. <c>MSFT</c>.</param>
    /// <param name="action">Either <c>buy</c> or <c>sell</c>.</param>
    /// <param name="quantity">The number of shares to trade.</param>
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
    // </place_trade>

    /// <summary>
    /// Creates an approval-required <see cref="AIFunction"/> for <see cref="PlaceTrade"/>.
    /// Wrapping the function in <see cref="ApprovalRequiredAIFunction"/> tells the harness to
    /// surface an approval request before the function ever runs.
    /// </summary>
    public static AIFunction CreatePlaceTradeTool() =>
        new ApprovalRequiredAIFunction(AIFunctionFactory.Create(PlaceTrade, "place_trade"));
}
