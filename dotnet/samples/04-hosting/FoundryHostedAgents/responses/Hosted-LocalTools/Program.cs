// Copyright (c) Microsoft. All rights reserved.

// Seattle Hotel Agent - a hosted agent with local C# function tools. Demonstrates how to define
// and wire local tools that the LLM can invoke, a key advantage of code-based hosted agents over
// prompt agents. It is deployed to Foundry directly from source (code / ZIP upload), so the
// platform builds and runs your code with no container image.

using System.ComponentModel;
using System.Globalization;
using System.Text;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var endpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-local-tools";

// ── Hotel data ───────────────────────────────────────────────────────────────

Hotel[] seattleHotels =
[
    new("Contoso Suites", 189, 4.5, "Downtown"),
    new("Fabrikam Residences", 159, 4.2, "Pike Place Market"),
    new("Alpine Ski House", 249, 4.7, "Seattle Center"),
    new("Margie's Travel Lodge", 219, 4.4, "Waterfront"),
    new("Northwind Inn", 139, 4.0, "Capitol Hill"),
    new("Relecloud Hotel", 99, 3.8, "University District"),
];

// ── Tool: GetAvailableHotels ─────────────────────────────────────────────────

[Description("Get available hotels in Seattle for the specified dates.")]
string GetAvailableHotels(
    [Description("Check-in date in YYYY-MM-DD format")] string checkInDate,
    [Description("Check-out date in YYYY-MM-DD format")] string checkOutDate,
    [Description("Maximum price per night in USD (optional, defaults to 500)")] int maxPrice = 500)
{
    if (!DateTime.TryParseExact(checkInDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var checkIn))
    {
        return "Error parsing check-in date. Please use YYYY-MM-DD format.";
    }

    if (!DateTime.TryParseExact(checkOutDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var checkOut))
    {
        return "Error parsing check-out date. Please use YYYY-MM-DD format.";
    }

    if (checkOut <= checkIn)
    {
        return "Error: Check-out date must be after check-in date.";
    }

    int nights = (checkOut - checkIn).Days;
    List<Hotel> availableHotels = seattleHotels.Where(h => h.PricePerNight <= maxPrice).ToList();

    if (availableHotels.Count == 0)
    {
        return $"No hotels found in Seattle within your budget of ${maxPrice}/night.";
    }

    StringBuilder result = new();
    result.AppendLine($"Available hotels in Seattle from {checkInDate} to {checkOutDate} ({nights} nights):");
    result.AppendLine();

    foreach (Hotel hotel in availableHotels)
    {
        int totalCost = hotel.PricePerNight * nights;
        result.AppendLine($"**{hotel.Name}**");
        result.AppendLine($"   Location: {hotel.Location}");
        result.AppendLine($"   Rating: {hotel.Rating}/5");
        result.AppendLine($"   ${hotel.PricePerNight}/night (Total: ${totalCost})");
        result.AppendLine();
    }

    return result.ToString();
}

// ── Create and host the agent ────────────────────────────────────────────────

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: deploymentName,
        instructions: """
            You are a helpful travel assistant specializing in finding hotels in Seattle, Washington.

            When a user asks about hotels in Seattle:
            1. Ask for their check-in and check-out dates if not provided
            2. Ask about their budget preferences if not mentioned
            3. Use the GetAvailableHotels tool to find available options
            4. Present the results in a friendly, informative way
            5. Offer to help with additional questions about the hotels or Seattle

            Be conversational and helpful. If users ask about things outside of Seattle hotels,
            politely let them know you specialize in Seattle hotel recommendations.
            """,
        name: agentName,
        description: "Seattle hotel search agent with local function tools",
        tools: [AIFunctionFactory.Create(GetAvailableHotels)]);

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;

// ── Types ────────────────────────────────────────────────────────────────────

internal sealed record Hotel(string Name, int PricePerNight, double Rating, string Location);
