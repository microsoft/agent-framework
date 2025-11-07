// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools.
// It shows both non-streaming and streaming agent interactions using weather-related tools.

using System.ComponentModel;
using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var agentsClient = new AgentsClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent with function tools.
var tool = AIFunctionFactory.Create(GetWeather);

// Create AIAgent directly
AIAgent agent = await agentsClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", thread));

// Streaming agent interaction with function tools.
thread = agent.GetNewThread();
await foreach (var update in agent.RunStreamingAsync("What is the weather like in Amsterdam?", thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
agentsClient.DeleteAgent(agent.Name);
