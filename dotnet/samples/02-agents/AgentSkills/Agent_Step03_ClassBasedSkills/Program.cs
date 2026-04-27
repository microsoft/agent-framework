// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to define Agent Skills as C# classes using AgentClassSkill
// with attributes for automatic script and resource discovery.

using System.ComponentModel;
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
/// A unit-converter skill defined as a C# class using attributes for discovery.
/// </summary>
/// <remarks>
/// Properties annotated with <see cref="AgentSkillResourceAttribute"/> are automatically
/// discovered as skill resources, and methods annotated with <see cref="AgentSkillScriptAttribute"/>
/// are automatically discovered as skill scripts. Alternatively,
/// <see cref="AgentSkill.Resources"/> and <see cref="AgentSkill.Scripts"/> can be overridden.
/// </remarks>
internal sealed class UnitConverterSkill : AgentClassSkill<UnitConverterSkill>
{
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

    /// <summary>
    /// Gets the <see cref="JsonSerializerOptions"/> used to marshal parameters and return values
    /// for scripts and resources.
    /// </summary>
    /// <remarks>
    /// This override is not necessary for this sample, but can be used to provide custom
    /// serialization options, for example a source-generated <c>JsonTypeInfoResolver</c>
    /// for Native AOT compatibility.
    /// </remarks>
    protected override JsonSerializerOptions? SerializerOptions => null;

    /// <summary>
    /// A conversion table resource providing multiplication factors.
    /// </summary>
    [AgentSkillResource("conversion-table")]
    [Description("Lookup table of multiplication factors for common unit conversions.")]
    public string ConversionTable => """
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
    /// Converts a value by the given factor.
    /// </summary>
    [AgentSkillScript("convert")]
    [Description("Multiplies a value by a conversion factor and returns the result as JSON.")]
    private static string ConvertUnits(double value, double factor)
    {
        double result = Math.Round(value * factor, 4);
        return JsonSerializer.Serialize(new { value, factor, result });
    }
}
