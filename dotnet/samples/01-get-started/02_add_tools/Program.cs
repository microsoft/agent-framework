// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an AIProjectClient agent with function tools.
// It shows both non-streaming and streaming agent interactions using weather tools.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the agent and provide the function tool to the agent.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(model: model, instructions: "You are a helpful assistant", tools: [AIFunctionFactory.Create(GetWeather)]);

// Non-streaming agent interaction with function tools.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));

// Streaming agent interaction with function tools.
await foreach (var update in agent.RunStreamingAsync("What is the weather like in Amsterdam?"))
{
    Console.WriteLine(update);
}
