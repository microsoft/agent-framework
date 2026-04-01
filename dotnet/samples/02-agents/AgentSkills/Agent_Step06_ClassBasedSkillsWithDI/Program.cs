// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Dependency Injection (DI) with class-based Agent Skills.
// Unlike code-defined skills (Step05), class-based skills bundle all components into a single
// class extending AgentClassSkill. Skill script and resource functions can still resolve
// services from the DI container via IServiceProvider, combining class-based organization
// with the flexibility of DI.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// --- Class-Based Skill with DI ---
// Instantiate the skill class. Its resources and scripts will resolve services from
// the DI container at execution time.
var unitConverter = new UnitConverterSkill();

// --- Skills Provider ---
var skillsProvider = new AgentSkillsProvider(unitConverter);

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
Console.WriteLine("Converting units with DI-powered class-based skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

/// <summary>
/// A unit-converter skill defined as a C# class that uses Dependency Injection.
/// </summary>
/// <remarks>
/// This skill resolves <see cref="ConversionRateService"/> from the DI container
/// in both its resource and script functions. This enables clean separation of
/// concerns and testability while retaining the class-based skill pattern.
/// </remarks>
internal sealed class UnitConverterSkill : AgentClassSkill
{
    private IReadOnlyList<AgentSkillResource>? _resources;
    private IReadOnlyList<AgentSkillScript>? _scripts;

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; } = new(
        "unit-converter",
        "Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.");

    /// <inheritdoc/>
    protected override string Instructions => """
        Use this skill when the user asks to convert between units.

        1. Review the conversion-table resource to find the factor for the requested conversion.
        2. Use the convert script, passing the value and factor from the table.
        3. Present the result clearly with both units.
        """;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
    [
        // Dynamic resource with DI: resolves ConversionRateService to build conversion table
        CreateResource("conversion-table", (IServiceProvider serviceProvider) =>
        {
            var rateService = serviceProvider.GetRequiredService<ConversionRateService>();
            return rateService.GetConversionTable();
        }),
    ];

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
    [
        // Script with DI: resolves ConversionRateService to perform the conversion
        CreateScript("convert", (double value, double factor, IServiceProvider serviceProvider) =>
        {
            var rateService = serviceProvider.GetRequiredService<ConversionRateService>();
            return rateService.Convert(value, factor);
        }),
    ];
}

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
