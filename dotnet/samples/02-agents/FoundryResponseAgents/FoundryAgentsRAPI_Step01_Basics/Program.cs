// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and run a basic agent with a FoundryAgentClient.

using Azure.Identity;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a FoundryAgentClient.
FoundryResponsesAgent agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));