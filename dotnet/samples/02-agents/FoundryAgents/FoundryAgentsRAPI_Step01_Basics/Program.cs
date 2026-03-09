// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and run a basic agent with a FoundryAgentClient.

using Microsoft.Agents.AI.AzureAI;

// Create a FoundryResponsesAgent.
FoundryAgent agent = new(instructions: "You are good at telling jokes.", name: "JokerAgent");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
