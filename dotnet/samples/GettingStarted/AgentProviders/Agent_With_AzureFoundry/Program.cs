// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

// Get a client to create/retrieve server side agents with.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// You can create a server side persistent agent with the Azure.AI.Agents.Persistent SDK.
var agentMetadata = await persistentAgentsClient.Administration.CreateAgentAsync(
    model: model,
    name: JokerName,
    instructions: JokerInstructions);

// You can retrieve an already created server side persistent agent as an AIAgent.
AIAgent agent1 = await persistentAgentsClient.GetAIAgentAsync(agentMetadata.Value.Id);

// You can also create a server side persistent agent and return it as an AIAgent directly.
AIAgent agent2 = await persistentAgentsClient.CreateAIAgentAsync(
    model: model,
    name: JokerName,
    instructions: JokerInstructions);

// You can then invoke the agent like any other AIAgent.
AgentThread thread = agent1.GetNewThread();
Console.WriteLine(await agent1.RunAsync("Tell me a joke about a pirate.", thread));

// Cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent1.Id);
await persistentAgentsClient.Administration.DeleteAgentAsync(agent2.Id);
