// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools.
// It shows both non-streaming and streaming agent interactions using weather-related tools.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Define the agent with function tools.
AITool tool = AIFunctionFactory.Create(GetWeather);

// Create AIAgent directly
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", thread));

// Streaming agent interaction with function tools.
thread = agent.GetNewThread();
await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync("What is the weather like in Amsterdam?", thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
