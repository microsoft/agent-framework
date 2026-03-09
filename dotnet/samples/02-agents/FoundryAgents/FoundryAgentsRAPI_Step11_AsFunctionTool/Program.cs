// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use one agent as a function tool for another agent.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

AITool weatherTool = AIFunctionFactory.Create(GetWeather);
FoundryAgent weatherAgent = new(
    instructions: "You answer questions about the weather.",
    name: "WeatherAgent",
    tools: [weatherTool]);

FoundryAgent agent = new(
    instructions: "You are a helpful assistant who responds in French.",
    name: "MainAgent",
    tools: [weatherAgent.AsAIFunction()]);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));
