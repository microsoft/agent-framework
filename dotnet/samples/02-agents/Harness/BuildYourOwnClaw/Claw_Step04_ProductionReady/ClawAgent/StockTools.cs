// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;

namespace ClawAgent;

/// <summary>
/// A custom function tool that gives the claw access to illustrative stock prices.
/// </summary>
internal static class StockTools
{
    /// <summary>
    /// A delayed, illustrative stock quote, including trailing earnings-per-share.
    /// </summary>
    public sealed record StockQuote(string Symbol, decimal Price, decimal TrailingEps, string Currency, DateTimeOffset AsOf);

    private static readonly Dictionary<string, (decimal Price, decimal Eps)> s_priceBook = new(StringComparer.OrdinalIgnoreCase)
    {
        ["MSFT"] = (462.97m, 11.80m),
        ["AAPL"] = (229.35m, 6.13m),
        ["GOOGL"] = (178.12m, 7.54m),
        ["AMZN"] = (201.45m, 4.18m),
        ["NVDA"] = (134.81m, 2.95m),
        ["SPY"] = (612.40m, 23.10m),
    };

    /// <summary>
    /// Gets the latest delayed, illustrative stock price and trailing EPS for a ticker symbol.
    /// </summary>
    [Description("Gets the latest (delayed, illustrative) stock price and trailing earnings per share for a ticker symbol.")]
    public static StockQuote GetStockPrice(
        [Description("The stock ticker symbol, e.g. MSFT or AAPL.")] string symbol)
    {
        if (!s_priceBook.TryGetValue(symbol, out var data))
        {
            var seed = 0;
            foreach (var ch in symbol.ToUpperInvariant())
            {
                seed = (seed * 31 + ch) % 1_000_000;
            }

            var price = 50m + seed % 45000 / 100m;
            data = (price, Math.Round(price / 20m, 2));
        }

        return new StockQuote(symbol.ToUpperInvariant(), data.Price, data.Eps, "USD", DateTimeOffset.UtcNow);
    }

    /// <summary>
    /// Creates the AI function wrapper used to expose the stock price tool to the agent.
    /// </summary>
    public static AIFunction CreateGetStockPriceTool() => AIFunctionFactory.Create(GetStockPrice, "get_stock_price");
}
