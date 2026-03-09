// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools.
// It shows both non-streaming and streaming agent interactions using weather-related tools.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Define the agent with function tools.
AITool tool = AIFunctionFactory.Create(GetWeather);

// Create AIAgent directly
FoundryVersionedAgent newAgent = await FoundryVersionedAgent.CreateAIAgentAsync(name: AssistantName, instructions: AssistantInstructions, tools: [tool]);

// Getting an already existing agent by name with tools.
/* 
 * IMPORTANT: Since agents that are stored in the server only know the definition of the function tools (JSON Schema),
 * you need to provided all invocable function tools when retrieving the agent so it can invoke them automatically.
 * If no invocable tools are provided, the function calling needs to handled manually.
 */
FoundryVersionedAgent existingAgent = await FoundryVersionedAgent.GetAIAgentAsync(name: AssistantName, tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentSession session = await existingAgent.CreateSessionAsync();
Console.WriteLine(await existingAgent.RunAsync("What is the weather like in Amsterdam?", session));

// Streaming agent interaction with function tools.
session = await existingAgent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in existingAgent.RunStreamingAsync("What is the weather like in Amsterdam?", session))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await FoundryVersionedAgent.DeleteAIAgentAsync(existingAgent);
