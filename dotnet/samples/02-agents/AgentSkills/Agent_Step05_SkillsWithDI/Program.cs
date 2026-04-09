// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Dependency Injection (DI) with Agent Skills.
// It shows two approaches side-by-side, each handling a different conversion domain:
//
// 1. Code-defined skill (AgentInlineSkill) — converts distances (miles ↔ kilometers).
//    Resources and scripts are inline delegates that resolve services from IServiceProvider.
//
// 2. Class-based skill (AgentClassSkill) — converts weights (pounds ↔ kilograms).
//    Resources and scripts are encapsulated in a class, also resolving services from IServiceProvider.
//
// Both skills share the same ConversionService registered in the DI container,
// showing that DI works identically regardless of how the skill is defined.
// When prompted with a question spanning both domains, the agent uses both skills.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// --- DI Container ---
// Register application services that skill resources and scripts can resolve at execution time.
ServiceCollection services = new();
services.AddSingleton<ConversionService>();

IServiceProvider serviceProvider = services.BuildServiceProvider();

// =====================================================================
// Approach 1: Code-Defined Skill with DI (AgentInlineSkill)
// =====================================================================
// Handles distance conversions (miles ↔ kilometers).
// Resources and scripts are inline delegates. Each delegate can declare
// an IServiceProvider parameter that the framework injects automatically.

var distanceSkill = new AgentInlineSkill(
    name: "distance-converter",
    description: "Convert between distance units. Use when asked to convert miles to kilometers or kilometers to miles.",
    instructions: """
        Use this skill when the user asks to convert between distance units (miles and kilometers).

        1. Review the distance-table resource to find the factor for the requested conversion.
        2. Use the convert script, passing the value and factor from the table.
        """)
    .AddResource("distance-table", (IServiceProvider serviceProvider) =>
    {
        var service = serviceProvider.GetRequiredService<ConversionService>();
        return service.GetDistanceTable();
    })
    .AddScript("convert", (double value, double factor, IServiceProvider serviceProvider) =>
    {
        var service = serviceProvider.GetRequiredService<ConversionService>();
        return service.Convert(value, factor);
    });

// =====================================================================
// Approach 2: Class-Based Skill with DI (AgentClassSkill)
// =====================================================================
// Handles weight conversions (pounds ↔ kilograms).
// Resources and scripts are encapsulated in a class. Factory methods
// CreateResource and CreateScript accept delegates with IServiceProvider.
//
// Alternatively, class-based skills can accept dependencies through their
// constructor. Register the skill class itself in the ServiceCollection and
// resolve it from the container:
//
//   services.AddSingleton<WeightConverterSkill>();
//   var weightSkill = serviceProvider.GetRequiredService<WeightConverterSkill>();

var weightSkill = new WeightConverterSkill();

// --- Skills Provider ---
// Both skills are registered with the same provider so the agent can use either one.
var skillsProvider = new AgentSkillsProvider(distanceSkill, weightSkill);

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
        services: serviceProvider);

// --- Example: Unit conversion ---
// This prompt spans both domains, so the agent will use both skills.
Console.WriteLine("Converting units with DI-powered skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

// ---------------------------------------------------------------------------
// Class-Based Skill
// ---------------------------------------------------------------------------

/// <summary>
/// A weight-converter skill defined as a C# class that uses Dependency Injection.
/// </summary>
/// <remarks>
/// This skill resolves <see cref="ConversionService"/> from the DI container
/// in both its resource and script functions. This enables clean separation of
/// concerns and testability while retaining the class-based skill pattern.
/// </remarks>
internal sealed class WeightConverterSkill : AgentClassSkill
{
    private IReadOnlyList<AgentSkillResource>? _resources;
    private IReadOnlyList<AgentSkillScript>? _scripts;

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; } = new(
        "weight-converter",
        "Convert between weight units. Use when asked to convert pounds to kilograms or kilograms to pounds.");

    /// <inheritdoc/>
    protected override string Instructions => """
        Use this skill when the user asks to convert between weight units (pounds and kilograms).

        1. Review the weight-table resource to find the factor for the requested conversion.
        2. Use the convert script, passing the value and factor from the table.
        3. Present the result clearly with both units.
        """;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
    [
        CreateResource("weight-table", (IServiceProvider serviceProvider) =>
        {
            var service = serviceProvider.GetRequiredService<ConversionService>();
            return service.GetWeightTable();
        }),
    ];

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
    [
        CreateScript("convert", (double value, double factor, IServiceProvider serviceProvider) =>
        {
            var service = serviceProvider.GetRequiredService<ConversionService>();
            return service.Convert(value, factor);
        }),
    ];
}

// ---------------------------------------------------------------------------
// Services
// ---------------------------------------------------------------------------

/// <summary>
/// Provides conversion rates between units.
/// In a real application this could call an external API, read from a database,
/// or apply time-varying exchange rates.
/// </summary>
internal sealed class ConversionService
{
    /// <summary>
    /// Returns a markdown table of supported distance conversions.
    /// </summary>
    public string GetDistanceTable() =>
        """
        # Distance Conversions

        Formula: **result = value × factor**

        | From        | To          | Factor   |
        |-------------|-------------|----------|
        | miles       | kilometers  | 1.60934  |
        | kilometers  | miles       | 0.621371 |
        """;

    /// <summary>
    /// Returns a markdown table of supported weight conversions.
    /// </summary>
    public string GetWeightTable() =>
        """
        # Weight Conversions

        Formula: **result = value × factor**

        | From        | To          | Factor   |
        |-------------|-------------|----------|
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
