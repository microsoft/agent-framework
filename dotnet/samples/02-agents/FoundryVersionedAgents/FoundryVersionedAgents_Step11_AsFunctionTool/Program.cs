// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an Microsoft Foundry Agents AI agent as a function tool.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

const string WeatherInstructions = "You answer questions about the weather.";
const string WeatherName = "WeatherAgent";
const string MainInstructions = "You are a helpful assistant who responds in French.";
const string MainName = "MainAgent";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the weather agent with function tools.
AITool weatherTool = AIFunctionFactory.Create(GetWeather);
FoundryVersionedAgent weatherAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    name: WeatherName,
    instructions: WeatherInstructions,
    tools: [weatherTool]);

// Create the main agent, and provide the weather agent as a function tool.
FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
    name: MainName,
    instructions: MainInstructions,
    tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));

// Cleanup by agent name removes the agent versions created.
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
await FoundryVersionedAgent.DeleteAIAgentAsync(weatherAgent);
