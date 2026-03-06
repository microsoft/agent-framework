// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use function tools with a FoundryAgentClient.

using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Define the function tool.
AITool tool = AIFunctionFactory.Create(GetWeather);

// Create a FoundryAgentClient with function tools.
FoundryResponsesAgent agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    model: deploymentName,
    instructions: "You are a helpful assistant that can get weather information.",
    name: "WeatherAssistant",
    tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));

// Streaming agent interaction with function tools.
session = await agent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("What is the weather like in Amsterdam?", session))
{
    Console.Write(update);
}

Console.WriteLine();
