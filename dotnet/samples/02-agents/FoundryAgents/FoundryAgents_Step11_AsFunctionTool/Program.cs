// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an Azure Foundry Agents AI agent as a function tool.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string WeatherInstructions = "You answer questions about the weather.";
const string WeatherName = "WeatherAgent";
const string MainInstructions = "You are a helpful assistant who responds in French.";
const string MainName = "MainAgent";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create the weather agent with function tools.
AITool weatherTool = AIFunctionFactory.Create(GetWeather);
AIAgent weatherAgent = await aiProjectClient.CreateAIAgentAsync(
    name: WeatherName,
    model: deploymentName,
    instructions: WeatherInstructions,
    tools: [weatherTool]);

// Create the main agent, and provide the weather agent as a function tool.
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: MainName,
    model: deploymentName,
    instructions: MainInstructions,
    tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));

// Cleanup by agent name removes the agent versions created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
await aiProjectClient.Agents.DeleteAgentAsync(weatherAgent.Name);
