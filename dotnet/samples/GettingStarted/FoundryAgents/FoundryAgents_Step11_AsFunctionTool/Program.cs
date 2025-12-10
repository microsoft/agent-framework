// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an Azure Foundry Agents AI agent as a function tool.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string WeatherInstructions = "You answer questions about the weather.";
const string WeatherName = "WeatherAgent";
const string MainInstructions = "You are a helpful assistant who responds in French.";
const string MainName = "MainAgent";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create the weather agent with function tools.
AITool weatherTool = AIFunctionFactory.Create(GetWeather);
AIAgent weatherAgent = aiProjectClient.CreateAIAgent(
    name: WeatherName,
    model: deploymentName,
    instructions: WeatherInstructions,
    tools: [weatherTool]);

// Create the main agent, and provide the weather agent as a function tool.
AIAgent agent = aiProjectClient.CreateAIAgent(
    name: MainName,
    model: deploymentName,
    instructions: MainInstructions,
    tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", thread));

// Cleanup by agent name removes the agent versions created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
await aiProjectClient.Agents.DeleteAgentAsync(weatherAgent.Name);
