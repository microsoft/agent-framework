// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates an advanced scenario: combining multiple skill types in a single agent
// using AgentSkillsProviderBuilder. The builder is designed for cases where the simple
// AgentSkillsProvider constructors are insufficient — for example, when you need to mix skill
// sources, apply filtering, or configure cross-cutting options in one place.
//
// Three different skill sources are registered here:
// 1. File-based: unit-converter (miles↔km, pounds↔kg) from SKILL.md on disk
// 2. Code-defined: volume-converter (gallons↔liters) using AgentInlineSkill
// 3. Class-based: temperature-converter (°F↔°C↔K) using AgentClassSkill
//
// For simpler, single-source scenarios, see the earlier steps in this sample series
// (e.g., Step01 for file-based, Step02 for code-defined, Step03 for class-based).

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// --- 1. Code-Defined Skill: volume-converter ---
var volumeConverterSkill = new AgentInlineSkill(
    name: "volume-converter",
    description: "Convert between gallons and liters using a multiplication factor.",
    instructions: """
        Use this skill when the user asks to convert between gallons and liters.

        1. Review the volume-conversion-table resource to find the correct factor.
        2. Use the convert-volume script, passing the value and factor.
        """)
    .AddResource("volume-conversion-table",
        """
        # Volume Conversion Table

        Formula: **result = value × factor**

        | From    | To      | Factor  |
        |---------|---------|---------|
        | gallons | liters  | 3.78541 |
        | liters  | gallons | 0.264172|
        """)
    .AddScript("convert-volume", (double value, double factor) =>
    {
        double result = Math.Round(value * factor, 4);
        return JsonSerializer.Serialize(new { value, factor, result });
    });

// --- 2. Class-Based Skill: temperature-converter ---
var temperatureConverter = new TemperatureConverterSkill();

// --- 3. Build provider combining all three source types ---
var skillsProvider = new AgentSkillsProviderBuilder()
    .UseFileSkill(Path.Combine(AppContext.BaseDirectory, "skills"))    // File-based: unit-converter
    .UseSkill(volumeConverterSkill)                                    // Code-defined: volume-converter
    .UseSkill(temperatureConverter)                                     // Class-based: temperature-converter
    .UseFileScriptRunner(SubprocessScriptRunner.RunAsync)
    .Build();

// --- Agent Setup ---
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "MultiConverterAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that can convert units, volumes, and temperatures.",
        },
        AIContextProviders = [skillsProvider],
    },
    model: deploymentName);

// --- Example: Use all three skills ---
Console.WriteLine("Converting with mixed skills (file + code + class)");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "I need three conversions: " +
    "1) How many kilometers is a marathon (26.2 miles)? " +
    "2) How many liters is a 5-gallon bucket? " +
    "3) What is 98.6°F in Celsius?");

Console.WriteLine($"Agent: {response.Text}");

/// <summary>
/// A temperature-converter skill defined as a C# class.
/// </summary>
internal sealed class TemperatureConverterSkill : AgentClassSkill
{
    private IReadOnlyList<AgentSkillResource>? _resources;
    private IReadOnlyList<AgentSkillScript>? _scripts;

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; } = new(
        "temperature-converter",
        "Convert between temperature scales (Fahrenheit, Celsius, Kelvin).");

    /// <inheritdoc/>
    protected override string Instructions => """
        Use this skill when the user asks to convert temperatures.

        1. Review the temperature-conversion-formulas resource for the correct formula.
        2. Use the convert-temperature script, passing the value, source scale, and target scale.
        3. Present the result clearly with both temperature scales.
        """;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
    [
        CreateResource(
            "temperature-conversion-formulas",
            """
            # Temperature Conversion Formulas

            | From        | To          | Formula                   |
            |-------------|-------------|---------------------------|
            | Fahrenheit  | Celsius     | °C = (°F − 32) × 5/9     |
            | Celsius     | Fahrenheit  | °F = (°C × 9/5) + 32     |
            | Celsius     | Kelvin      | K = °C + 273.15           |
            | Kelvin      | Celsius     | °C = K − 273.15           |
            """),
    ];

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
    [
        CreateScript("convert-temperature", ConvertTemperature),
    ];

    private static string ConvertTemperature(double value, string from, string to)
    {
        double result = (from.ToUpperInvariant(), to.ToUpperInvariant()) switch
        {
            ("FAHRENHEIT", "CELSIUS") => Math.Round((value - 32) * 5.0 / 9.0, 2),
            ("CELSIUS", "FAHRENHEIT") => Math.Round(value * 9.0 / 5.0 + 32, 2),
            ("CELSIUS", "KELVIN") => Math.Round(value + 273.15, 2),
            ("KELVIN", "CELSIUS") => Math.Round(value - 273.15, 2),
            _ => throw new ArgumentException($"Unsupported conversion: {from} → {to}")
        };

        return JsonSerializer.Serialize(new { value, from, to, result });
    }
}
