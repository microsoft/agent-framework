// Copyright (c) Microsoft. All rights reserved.

// Seattle Hotel Agent - A simple agent with a tool to find hotels in Seattle.
// Uses Microsoft Agent Framework with Microsoft Foundry.
// Ready for deployment to Foundry Hosted Agent service.

#pragma warning disable CA2252 // AIProjectClient and Agents API require opting into preview features

using System.ComponentModel;
using System.Globalization;
using System.Text;

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// Get configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
Console.WriteLine($"Project Endpoint: {endpoint}");
Console.WriteLine($"Model Deployment: {deploymentName}");
// Simulated hotel data for Seattle
var seattleHotels = new[]
{
    new Hotel("Contoso Suites", 189, 4.5, "Downtown"),
    new Hotel("Fabrikam Residences", 159, 4.2, "Pike Place Market"),
    new Hotel("Alpine Ski House", 249, 4.7, "Seattle Center"),
    new Hotel("Margie's Travel Lodge", 219, 4.4, "Waterfront"),
    new Hotel("Northwind Inn", 139, 4.0, "Capitol Hill"),
    new Hotel("Relecloud Hotel", 99, 3.8, "University District"),
};

[Description("Get available hotels in Seattle for the specified dates. This simulates a call to a hotel availability API.")]
string GetAvailableHotels(
    [Description("Check-in date in YYYY-MM-DD format")] string checkInDate,
    [Description("Check-out date in YYYY-MM-DD format")] string checkOutDate,
    [Description("Maximum price per night in USD (optional, defaults to 500)")] int maxPrice = 500)
{
    try
    {
        // Parse dates
        if (!DateTime.TryParseExact(checkInDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var checkIn))
        {
            return "Error parsing check-in date. Please use YYYY-MM-DD format.";
        }

        if (!DateTime.TryParseExact(checkOutDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var checkOut))
        {
            return "Error parsing check-out date. Please use YYYY-MM-DD format.";
        }

        // Validate dates
        if (checkOut <= checkIn)
        {
            return "Error: Check-out date must be after check-in date.";
        }

        var nights = (checkOut - checkIn).Days;

        // Filter hotels by price
        var availableHotels = seattleHotels.Where(h => h.PricePerNight <= maxPrice).ToList();

        if (availableHotels.Count == 0)
        {
            return $"No hotels found in Seattle within your budget of ${maxPrice}/night.";
        }

        // Build response
        var result = new StringBuilder();
        result
            .AppendLine($"Available hotels in Seattle from {checkInDate} to {checkOutDate} ({nights} nights):")
            .AppendLine();

        foreach (var hotel in availableHotels)
        {
            var totalCost = hotel.PricePerNight * nights;
            result
                .AppendLine($"**{hotel.Name}**")
                .AppendLine($"   Location: {hotel.Location}")
                .AppendLine($"   Rating: {hotel.Rating}/5")
                .AppendLine($"   ${hotel.PricePerNight}/night (Total: ${totalCost})")
                .AppendLine();
        }

        return result.ToString();
    }
    catch (Exception ex)
    {
        return $"Error processing request. Details: {ex.Message}";
    }
}

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create Foundry agent with hotel search tool
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "SeattleHotelAgent",
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
    tools: [AIFunctionFactory.Create(GetAvailableHotels)]);

try
{
    Console.WriteLine("Seattle Hotel Agent Server running on http://localhost:8088");
    await agent.RunAIAgentAsync(telemetrySourceName: "Agents");
}
finally
{
    // Cleanup server-side agent
    await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
}

// Hotel record for simulated data
internal sealed record Hotel(string Name, int PricePerNight, double Rating, string Location);
