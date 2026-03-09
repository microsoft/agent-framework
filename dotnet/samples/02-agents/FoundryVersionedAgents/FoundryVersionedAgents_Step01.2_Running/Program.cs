// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Microsoft Foundry Agents as the backend.


using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Create a FoundryVersionedAgent — endpoint, credential, and model are auto-resolved from environment variables.
FoundryVersionedAgent jokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(name: JokerName, instructions: JokerInstructions);

// Invoke the agent with streaming support.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(jokerAgent);
