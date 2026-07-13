// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text;
using Microsoft.Extensions.AI;
using AgentMemory.Neo4j.Infrastructure;
using Neo4j.Driver;

namespace AgentMemoryShoppingAssistant;

/// <summary>
/// A small retail product graph plus the shopping tools that query it — the .NET counterpart of the
/// Python retail-assistant's <c>get_product_tools</c>. Products live in Neo4j as <c>:Product</c> nodes
/// linked to <c>:ProductCategory</c> / <c>:ProductBrand</c> nodes, so recommendations and "related
/// products" come from graph traversals. Cypher runs through the public <see cref="INeo4jTransactionRunner"/>
/// seam. Exposed as <see cref="AIFunction"/>s so a real chat model can call them during a run — the same
/// way <c>MemoryToolFactory.CreateAIFunctions()</c> exposes the memory tools.
/// </summary>
public sealed class ProductCatalog(INeo4jTransactionRunner runner)
{
    private readonly INeo4jTransactionRunner _runner = runner;

    private static readonly (string Name, string Category, string Brand, double Price, bool InStock, int Inventory, string Description, int Popularity)[] Seed =
    [
        ("Nike Air Zoom Pegasus 40", "shoes",       "Nike",   130, true,  40, "Everyday running shoe with responsive cushioning.",   95),
        ("Nike Revolution 7",        "shoes",       "Nike",    70, true,  60, "Lightweight, budget-friendly running shoe.",          80),
        ("Adidas Ultraboost Light",  "shoes",       "Adidas",  190, true, 25, "Premium running shoe with Boost cushioning.",         90),
        ("Asics Gel-Kayano 31",      "shoes",       "Asics",   165, false,  0, "Stability running shoe for overpronation.",           70),
        ("Sony WH-1000XM5",          "electronics", "Sony",    350, true,  18, "Industry-leading noise-cancelling headphones.",       92),
        ("Bose QuietComfort Ultra",  "electronics", "Bose",    330, true,  12, "Premium noise-cancelling over-ear headphones.",       85),
        ("Apple AirPods Pro 2",      "electronics", "Apple",   250, true,  50, "Wireless earbuds with active noise cancellation.",    88),
        ("Garmin Forerunner 265",    "electronics", "Garmin",  450, true,   9, "GPS running watch with training metrics.",            78),
        ("Nike Dri-FIT Running Tee", "apparel",     "Nike",     35, true, 120, "Breathable, moisture-wicking running shirt.",         65),
        ("Adidas Own the Run Jacket","apparel",     "Adidas",   80, true,  33, "Lightweight, water-repellent running jacket.",        60),
    ];

    /// <summary>Seeds the sample product graph (idempotent — safe to run every start).</summary>
    public Task SeedAsync(CancellationToken ct = default) => _runner.WriteAsync(async r =>
    {
        await r.RunAsync(
            """
            UNWIND $products AS row
            MERGE (p:Product {name: row.name})
              SET p.category = row.category, p.brand = row.brand, p.price = row.price,
                  p.in_stock = row.in_stock, p.inventory = row.inventory,
                  p.description = row.description, p.popularity = row.popularity
            MERGE (c:ProductCategory {name: row.category})
            MERGE (b:ProductBrand {name: row.brand})
            MERGE (p)-[:IN_CATEGORY]->(c)
            MERGE (p)-[:MADE_BY]->(b)
            """,
            new
            {
                products = Seed.Select(p => (object)new Dictionary<string, object>
                {
                    ["name"] = p.Name, ["category"] = p.Category, ["brand"] = p.Brand, ["price"] = p.Price,
                    ["in_stock"] = p.InStock, ["inventory"] = p.Inventory, ["description"] = p.Description,
                    ["popularity"] = p.Popularity,
                }).ToList(),
            });
    }, ct);

    // ── Tools (also usable directly in the scripted demo) ────────────────────────────────────────

    [Description("Search the product catalog for items matching a query, with optional category, brand, and max-price filters.")]
    public Task<string> SearchProductsAsync(
        [Description("What the customer is looking for, e.g. 'running shoes'.")] string query,
        [Description("Optional category filter: shoes, electronics, apparel.")] string? category = null,
        [Description("Optional brand filter, e.g. 'Nike'.")] string? brand = null,
        [Description("Optional maximum price.")] double? maxPrice = null,
        CancellationToken ct = default) => _runner.ReadAsync(async r =>
    {
        var cypher =
            """
            MATCH (p:Product)
            WHERE ANY(w IN split(toLower($query), ' ') WHERE
                      toLower(p.name) CONTAINS w OR toLower(p.description) CONTAINS w OR toLower(p.category) CONTAINS w)
              AND ($category IS NULL OR p.category = $category)
              AND ($brand    IS NULL OR p.brand = $brand)
              AND ($maxPrice IS NULL OR p.price <= $maxPrice)
            RETURN p.name AS name, p.brand AS brand, p.category AS category,
                   p.price AS price, p.in_stock AS inStock
            ORDER BY p.popularity DESC
            LIMIT 10
            """;
        var cursor = await r.RunAsync(cypher, new { query, category, brand, maxPrice });
        return Render("Matches", await cursor.ToListAsync());
    }, ct);

    [Description("Get personalized product recommendations, optionally biased toward a preferred brand and/or category.")]
    public Task<string> GetRecommendationsAsync(
        [Description("The customer's preferred brand (from their saved preferences), if known.")] string? preferredBrand = null,
        [Description("Optional category to recommend within.")] string? category = null,
        [Description("How many recommendations to return.")] int limit = 5,
        CancellationToken ct = default) => _runner.ReadAsync(async r =>
    {
        var cypher =
            """
            MATCH (p:Product)
            WHERE p.in_stock = true
              AND ($category IS NULL OR p.category = $category)
            WITH p, (CASE WHEN $preferredBrand IS NOT NULL AND p.brand = $preferredBrand THEN 1 ELSE 0 END) AS onBrand
            RETURN p.name AS name, p.brand AS brand, p.category AS category, p.price AS price, p.in_stock AS inStock
            ORDER BY onBrand DESC, p.popularity DESC
            LIMIT $limit
            """;
        var cursor = await r.RunAsync(cypher, new { preferredBrand, category, limit });
        var header = preferredBrand is null ? "Recommended for you" : $"Recommended for you (favoring {preferredBrand})";
        return Render(header, await cursor.ToListAsync());
    }, ct);

    [Description("Find products related to a given product — same category or same brand — via graph traversal.")]
    public Task<string> GetRelatedProductsAsync(
        [Description("The exact product name to find related items for.")] string productName,
        CancellationToken ct = default) => _runner.ReadAsync(async r =>
    {
        var cypher =
            """
            MATCH (p:Product {name: $productName})
            CALL (p) {
                MATCH (p)-[:IN_CATEGORY]->(c)<-[:IN_CATEGORY]-(rel:Product) WHERE rel <> p
                RETURN rel, 'same category' AS reason
              UNION
                MATCH (p)-[:MADE_BY]->(b)<-[:MADE_BY]-(rel:Product) WHERE rel <> p
                RETURN rel, 'same brand' AS reason
            }
            WITH rel, collect(DISTINCT reason) AS reasons
            RETURN rel.name AS name, rel.brand AS brand, rel.category AS category,
                   rel.price AS price, rel.in_stock AS inStock, rel.popularity AS popularity,
                   reduce(s = '', x IN reasons | CASE WHEN s = '' THEN x ELSE s + ', ' + x END) AS reason
            ORDER BY popularity DESC
            LIMIT 5
            """;
        var cursor = await r.RunAsync(cypher, new { productName });
        return Render($"Related to {productName}", await cursor.ToListAsync());
    }, ct);

    [Description("Check whether a product is in stock and how many units are available.")]
    public Task<string> CheckInventoryAsync(
        [Description("The exact product name to check.")] string productName,
        CancellationToken ct = default) => _runner.ReadAsync(async r =>
    {
        var cursor = await r.RunAsync(
            "MATCH (p:Product {name: $productName}) RETURN p.name AS name, p.in_stock AS inStock, p.inventory AS inventory",
            new { productName });
        var rows = await cursor.ToListAsync();
        if (rows.Count == 0) return $"'{productName}' was not found in the catalog.";
        var rec = rows[0];
        var inStock = rec["inStock"].As<bool>();
        return inStock
            ? $"{rec["name"].As<string>()}: In stock ({rec["inventory"].As<long>()} available)."
            : $"{rec["name"].As<string>()}: Out of stock.";
    }, ct);

    /// <summary>The retail tools as MAF/MEAI <see cref="AIFunction"/>s (attach to the agent's ChatOptions.Tools).</summary>
    public IReadOnlyList<AIFunction> CreateAIFunctions() =>
    [
        AIFunctionFactory.Create(SearchProductsAsync, "search_products",
            "Search the product catalog with optional category/brand/price filters."),
        AIFunctionFactory.Create(GetRecommendationsAsync, "get_recommendations",
            "Get personalized recommendations, optionally favoring a preferred brand/category."),
        AIFunctionFactory.Create(GetRelatedProductsAsync, "get_related_products",
            "Find products related to a given product via the graph."),
        AIFunctionFactory.Create(CheckInventoryAsync, "check_inventory",
            "Check stock/availability for a product."),
    ];

    private static string Render(string header, IReadOnlyList<IRecord> rows)
    {
        if (rows.Count == 0) return $"{header}: (no matches)";
        var sb = new StringBuilder().Append(header).Append(':').AppendLine();
        foreach (var rec in rows)
        {
            var stock = rec["inStock"].As<bool>() ? "in stock" : "out of stock";
            var reason = rec.Keys.Contains("reason") ? $"  [{rec["reason"].As<string>()}]" : string.Empty;
            sb.Append("  • ")
              .Append(rec["name"].As<string>())
              .Append(" — ").Append(rec["brand"].As<string>())
              .Append(", ").Append(rec["category"].As<string>())
              .Append(", $").Append(rec["price"].As<double>().ToString("0"))
              .Append(", ").Append(stock).Append(reason)
              .AppendLine();
        }
        return sb.ToString().TrimEnd();
    }
}
