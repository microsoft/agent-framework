// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve server side agents with.
var agentsClient = new AgentsClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create.
var agentDefinition = new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions };

// You can create a server side agent with the Azure.AI.Agents SDK.
var agentVersion = agentsClient.CreateAgentVersion(agentName: JokerName, definition: agentDefinition).Value;

// You can retrieve an already created server side agent as an AIAgent.
AIAgent existingAgent = await agentsClient.GetAIAgentAsync(agentVersion.Name);

// You can also create a server side persistent agent and return it as an AIAgent directly.
var createdAgent = agentsClient.CreateAIAgent(name: JokerName, model: deploymentName, instructions: JokerInstructions);

// You can then invoke the agent like any other AIAgent.
AgentThread thread = existingAgent.GetNewThread();
Console.WriteLine(await existingAgent.RunAsync("Tell me a joke about a pirate.", thread));

// Cleanup by agent name (removes both agent versions created by existingAgent + createdAgent).
await agentsClient.DeleteAgentAsync(agentVersion.Name);
