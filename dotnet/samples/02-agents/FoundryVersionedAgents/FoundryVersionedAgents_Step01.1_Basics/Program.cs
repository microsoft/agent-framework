// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use AI agents with Microsoft Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

const string JokerName = "JokerAgent";

// Create a FoundryVersionedAgent — endpoint, credential, and model are auto-resolved from environment variables.
FoundryVersionedAgent jokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    name: JokerName,
    instructions: "You are good at telling jokes.");

// You can also create another version by providing the same name with a different instruction.
FoundryVersionedAgent newJokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    name: JokerName,
    instructions: "You are extremely hilarious at telling jokes.");

// You can also get the latest version by just providing its name.
FoundryVersionedAgent jokerAgentLatest = await FoundryVersionedAgent.GetAIAgentAsync(name: JokerName);
AgentVersion latestAgentVersion = jokerAgentLatest.GetService<AgentVersion>()!;

// The AgentVersion can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate."));

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(jokerAgentLatest);
