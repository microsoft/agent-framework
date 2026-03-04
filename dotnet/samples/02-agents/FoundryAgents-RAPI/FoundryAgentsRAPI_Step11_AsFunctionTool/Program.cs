// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use one agent as a function tool for another agent using the Responses API directly.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the weather agent with function tools using environment variable auto-discovery.
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
AITool weatherTool = AIFunctionFactory.Create(GetWeather);
FoundryAgentClient weatherAgent = new(
    instructions: "You answer questions about the weather.",
    name: "WeatherAgent",
    tools: [weatherTool]);

// Create the main agent, and provide the weather agent as a function tool.
FoundryAgentClient agent = new(
    instructions: "You are a helpful assistant who responds in French.",
    name: "MainAgent",
    tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));
