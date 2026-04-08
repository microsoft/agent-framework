// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to define Agent Skills as C# classes using AgentClassSkill.
// Class-based skills bundle all components into a single class implementation.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// --- Class-Based Skill ---
// Instantiate the skill class.
var unitConverter = new UnitConverterSkill();

// --- Skills Provider ---
var skillsProvider = new AgentSkillsProvider(unitConverter);

// --- Agent Setup ---
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "UnitConverterAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that can convert units.",
        },
        AIContextProviders = [skillsProvider],
    },
    model: deploymentName);

// --- Example: Unit conversion ---
Console.WriteLine("Converting units with class-based skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

/// <summary>
/// A unit-converter skill defined as a C# class.
/// </summary>
/// <remarks>
/// Class-based skills bundle all components (name, description, body, resources, scripts)
/// into a single class.
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
        CreateResource(
            "conversion-table",
            """
            # Conversion Tables

            Formula: **result = value × factor**

            | From        | To          | Factor   |
            |-------------|-------------|----------|
            | miles       | kilometers  | 1.60934  |
            | kilometers  | miles       | 0.621371 |
            | pounds      | kilograms   | 0.453592 |
            | kilograms   | pounds      | 2.20462  |
            """),
    ];

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
    [
        CreateScript("convert", ConvertUnits),
    ];

    private static string ConvertUnits(double value, double factor)
    {
        double result = Math.Round(value * factor, 4);
        return JsonSerializer.Serialize(new { value, factor, result });
    }
}
