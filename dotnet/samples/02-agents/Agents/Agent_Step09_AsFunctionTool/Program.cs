// Copyright (c) Microsoft. All rights reserved.

// Agent as Function Tool — Use one agent as a tool for another
//
// This sample shows how to create an AI agent and expose it as a
// function tool that another agent can call.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the agent and provide the function tool to it.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent weatherAgent = aiProjectClient
     .AsAIAgent(
        model: deploymentName,
        instructions: "You answer questions about the weather.",
        name: "WeatherAgent",
        description: "An agent that answers questions about the weather.",
        tools: [AIFunctionFactory.Create(GetWeather)]);

// Create the main agent, and provide the weather agent as a function tool.
AIAgent agent = aiProjectClient
    .AsAIAgent(
        model: deploymentName,
        instructions: "You are a helpful assistant who responds in French.",
        tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));
