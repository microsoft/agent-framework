// Copyright (c) Microsoft. All rights reserved.

// Seattle Hotel Agent - A hosted agent with local C# function tools.
// Demonstrates how to define and wire local tools that the LLM can invoke,
// a key advantage of code-based hosted agents over prompt agents.

using System.ComponentModel;
using System.Globalization;
using System.Text;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

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

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
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
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-local-tools",
        description: "Seattle hotel search agent with local function tools",
        tools: [AIFunctionFactory.Create(GetAvailableHotels)]);

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

// ── Types ────────────────────────────────────────────────────────────────────

internal sealed record Hotel(string Name, int PricePerNight, double Rating, string Location);

/// <summary>
/// A <see cref="TokenCredential"/> for local Docker debugging only.
/// Reads a pre-fetched bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable
/// once at startup. This should NOT be used in production.
///
/// Generate a token on your host and pass it to the container:
///   export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN ...
/// </summary>
internal sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string EnvironmentVariable = "AZURE_BEARER_TOKEN";
    private readonly string? _token;

    public DevTemporaryTokenCredential()
    {
        this._token = Environment.GetEnvironmentVariable(EnvironmentVariable);
    }

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => this.GetAccessToken();

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => new(this.GetAccessToken());

    private AccessToken GetAccessToken()
    {
        if (string.IsNullOrEmpty(this._token) || this._token == "DefaultAzureCredential")
        {
            throw new CredentialUnavailableException($"{EnvironmentVariable} environment variable is not set.");
        }

        return new AccessToken(this._token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
