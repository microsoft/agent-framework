// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and run a basic agent using the Foundry Responses API directly,
// without creating a server-side agent definition.

using Microsoft.Agents.AI.AzureAI;

// Create a FoundryAgentClient that uses the Responses API directly.
// No server-side agent is created — instructions and model are provided locally.
// The endpoint and model are resolved from environment variables:
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
// Authentication uses DefaultAzureCredential.
FoundryAgentClient agent = new(
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
