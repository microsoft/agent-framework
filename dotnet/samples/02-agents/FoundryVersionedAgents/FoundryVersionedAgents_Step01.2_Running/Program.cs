// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Microsoft Foundry Agents as the backend.

using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Create a FoundryVersionedAgent with explicit endpoint and credential.
FoundryVersionedAgent jokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    name: JokerName,
    model: deploymentName,
    instructions: JokerInstructions);

// Invoke the agent with streaming support.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(jokerAgent);
