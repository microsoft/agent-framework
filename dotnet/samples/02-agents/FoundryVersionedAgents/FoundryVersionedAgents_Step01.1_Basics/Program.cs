// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use AI agents with Microsoft Foundry Agents as the backend.

using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";

// Create a FoundryVersionedAgent with explicit endpoint and credential.
FoundryVersionedAgent jokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    name: JokerName,
    model: deploymentName,
    instructions: "You are good at telling jokes.");

// You can also create another version by providing the same name with a different instruction.
FoundryVersionedAgent newJokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    name: JokerName,
    model: deploymentName,
    instructions: "You are extremely hilarious at telling jokes.");

// You can also get the latest version by just providing its name.
FoundryVersionedAgent jokerAgentLatest = await FoundryVersionedAgent.GetAIAgentAsync(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    name: JokerName);
AgentVersion latestAgentVersion = jokerAgentLatest.GetService<AgentVersion>()!;

// The AgentVersion can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate."));

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(jokerAgentLatest);
