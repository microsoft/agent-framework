// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;

namespace ClawSample;

/// <summary>
/// A custom function tool that gives our "claw" access to (illustrative) stock prices.
/// </summary>
/// <remarks>
/// The prices returned here are mock data for demonstration purposes only and are not real
/// market quotes. In a real assistant you would call a market-data API instead.
/// </remarks>
internal static class StockTools
{
    // <stock_quote>
    /// <summary>A delayed, illustrative stock quote.</summary>
    public sealed record StockQuote(string Symbol, decimal Price, string Currency, DateTimeOffset AsOf);
    // </stock_quote>

    // A tiny in-memory price book so the sample runs without any external dependency.
    private static readonly Dictionary<string, decimal> s_priceBook = new(StringComparer.OrdinalIgnoreCase)
    {
        ["MSFT"] = 462.97m,
        ["AAPL"] = 229.35m,
        ["GOOGL"] = 178.12m,
        ["AMZN"] = 201.45m,
        ["NVDA"] = 134.81m,
    };

    // <get_stock_price>
    /// <summary>
    /// Gets the latest (delayed, illustrative) stock price for a ticker symbol.
    /// </summary>
    /// <param name="symbol">The stock ticker symbol, e.g. <c>MSFT</c> or <c>AAPL</c>.</param>
    [Description("Gets the latest (delayed, illustrative) stock price for a ticker symbol.")]
    public static StockQuote GetStockPrice(
        [Description("The stock ticker symbol, e.g. MSFT or AAPL.")] string symbol)
    {
        if (!s_priceBook.TryGetValue(symbol, out var price))
        {
            // Deterministic pseudo-price for unknown symbols so the sample stays self-contained.
            // Derive a stable seed from the characters — string.GetHashCode() is randomized per
            // process and Math.Abs(int.MinValue) throws, so neither is safe for repeatable output.
            var seed = 0;
            foreach (var ch in symbol.ToUpperInvariant())
            {
                seed = (seed * 31 + ch) % 1_000_000;
            }

            price = 50m + seed % 45000 / 100m;
        }

        return new StockQuote(symbol.ToUpperInvariant(), price, "USD", DateTimeOffset.UtcNow);
    }
    // </get_stock_price>

    /// <summary>Creates the <see cref="AIFunction"/> wrapper used to expose the tool to the agent.</summary>
    public static AIFunction CreateGetStockPriceTool() => AIFunctionFactory.Create(GetStockPrice, "get_stock_price");
}
