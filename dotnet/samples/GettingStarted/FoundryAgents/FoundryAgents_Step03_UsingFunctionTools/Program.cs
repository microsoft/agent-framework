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
var newAgent = await aiProjectClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: [tool]);

// Getting an already existing agent by name with tools.
/* 
 * IMPORTANT: Since agents that are stored in the server only know the definition of the function tools (JSON Schema),
 * you need to provided all invocable function tools when retrieving the agent so it can invoke them automatically.
 * If no invocable tools are provided, the function calling needs to handled manually.
 */
var existingAgent = await aiProjectClient.GetAIAgentAsync(name: AssistantName, tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentThread thread = existingAgent.GetNewThread();
Console.WriteLine(await existingAgent.RunAsync("What is the weather like in Amsterdam?", thread));

// Streaming agent interaction with function tools.
thread = existingAgent.GetNewThread();
await foreach (AgentRunResponseUpdate update in existingAgent.RunStreamingAsync("What is the weather like in Amsterdam?", thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(existingAgent.Name);
