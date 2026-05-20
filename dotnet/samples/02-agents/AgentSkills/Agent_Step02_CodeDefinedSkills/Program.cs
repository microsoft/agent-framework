// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to define Agent Skills entirely in code using AgentInlineSkill.
// No SKILL.md files are needed — skills, resources, and scripts are all defined programmatically.
//
// Three approaches are shown using a unit-converter skill:
// 1. Static resources — inline content provided via AddResource
// 2. Dynamic resources — computed at runtime via a factory delegate
// 3. Code scripts — executable delegates the agent can invoke directly

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// --- Build the code-defined skill ---
var unitConverterSkill = new AgentInlineSkill(
    name: "unit-converter",
    description: "Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.",
    instructions: """
        Use this skill when the user asks to convert between units.

        1. Review the conversion-table resource to find the factor for the requested conversion.
        2. Check the conversion-policy resource for rounding and formatting rules.
        3. Use the convert script, passing the value and factor from the table.
        """)
    // 1. Static Resource: conversion tables
    .AddResource(
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
        """)
    // 2. Dynamic Resource: conversion policy (computed at runtime)
    .AddResource("conversion-policy", () =>
    {
        const int Precision = 4;
        return $"""
            # Conversion Policy

            **Decimal places:** {Precision}
            **Format:** Always show both the original and converted values with units
            **Generated at:** {DateTime.UtcNow:O}
            """;
    })
    // 3. Code Script: convert
    .AddScript("convert", (double value, double factor) =>
    {
        double result = Math.Round(value * factor, 4);
        return JsonSerializer.Serialize(new { value, factor, result });
    });

// --- Skills Provider ---
var skillsProvider = new AgentSkillsProvider(unitConverterSkill);

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
Console.WriteLine("Converting units with code-defined skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");
