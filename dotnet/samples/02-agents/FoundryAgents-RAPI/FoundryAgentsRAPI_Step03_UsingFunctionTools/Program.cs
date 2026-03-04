// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use function tools with the Foundry Responses API directly.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Define the function tool.
AITool tool = AIFunctionFactory.Create(GetWeather);

// Create a FoundryAgentClient that uses the Responses API directly with function tools.
// No server-side agent is created — instructions, tools and model are provided locally.
// The endpoint and model are resolved from environment variables:
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
// Authentication uses DefaultAzureCredential.
FoundryAgentClient agent = new(
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
