// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Dependency Injection (DI) with Agent Skills.
// Skill script and resource functions can resolve services from the DI container via
// IServiceProvider, enabling clean separation of concerns and testability.
//
// The sample registers a ConversionRateService in the DI container. A code-defined skill
// resource resolves this service to list supported conversions dynamically, and a skill
// script resolves it to look up live conversion rates at execution time.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// --- Build the code-defined skill ---
// The skill uses DI to resolve ConversionRateService in both its resource and script functions.
var unitConverterSkill = new AgentInlineSkill(
    name: "unit-converter",
    description: "Convert between common units. Use when asked to convert miles, kilometers, pounds, or kilograms.",
    instructions: """
        Use this skill when the user asks to convert between units.

        1. Review the conversion-table resource to find the factor for the requested conversion.
        2. Check the conversion-policy resource for rounding and formatting rules.
        3. Use the convert script, passing the value and factor from the table.
        """)
    // Dynamic resource with DI: resolves ConversionRateService to build conversion table
    .AddResource("conversion-table", (IServiceProvider serviceProvider) =>
    {
        var rateService = serviceProvider.GetRequiredService<ConversionRateService>();
        return rateService.GetConversionTable();
    })
    // Script with DI: resolves ConversionRateService to perform the conversion
    .AddScript("convert", (double value, double factor, IServiceProvider serviceProvider) =>
    {
        var rateService = serviceProvider.GetRequiredService<ConversionRateService>();
        return rateService.Convert(value, factor);
    });

// --- Skills Provider ---
var skillsProvider = new AgentSkillsProvider(unitConverterSkill);

// --- DI Container ---
// Register application services that skill scripts can resolve at execution time.
ServiceCollection services = new();
services.AddSingleton<ConversionRateService>();

// --- Agent Setup ---
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(
        options: new ChatClientAgentOptions
        {
            Name = "UnitConverterAgent",
            ChatOptions = new()
            {
                Instructions = "You are a helpful assistant that can convert units.",
            },
            AIContextProviders = [skillsProvider],
        },
        model: deploymentName,
        services: services.BuildServiceProvider());

// --- Example: Unit conversion ---
Console.WriteLine("Converting units with DI-powered skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

// ---------------------------------------------------------------------------
// Services
// ---------------------------------------------------------------------------

/// <summary>
/// Provides conversion rates between units.
/// In a real application this could call an external API, read from a database,
/// or apply time-varying exchange rates.
/// </summary>
internal sealed class ConversionRateService
{
    /// <summary>
    /// Returns a static markdown table of all supported conversions with factors.
    /// </summary>
    public string GetConversionTable() =>
        """
        # Conversion Tables

        Formula: **result = value × factor**

        | From        | To          | Factor   |
        |-------------|-------------|----------|
        | miles       | kilometers  | 1.60934  |
        | kilometers  | miles       | 0.621371 |
        | pounds      | kilograms   | 0.453592 |
        | kilograms   | pounds      | 2.20462  |
        """;

    /// <summary>
    /// Converts a value by the given factor and returns a JSON result.
    /// </summary>
    public string Convert(double value, double factor)
    {
        double result = Math.Round(value * factor, 4);
        return JsonSerializer.Serialize(new { value, factor, result });
    }
}
