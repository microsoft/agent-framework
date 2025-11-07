// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var agentsClient = new AgentsClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
var agentDefinition = new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions };

// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
var agentVersion = agentsClient.CreateAgentVersion(agentName: JokerName, definition: agentDefinition);

// You can retrieve an AIAgent for a already created server side agent version.
AIAgent jokerAgent = agentsClient.GetAIAgent(agentVersion);

// Invoke the agent and output the text result.
AgentThread thread = jokerAgent.GetNewThread();
Console.WriteLine(await jokerAgent.RunAsync("Tell me a joke about a pirate.", thread));

// Invoke the agent with streaming support.
thread = jokerAgent.GetNewThread();
await foreach (var update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate.", thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
agentsClient.DeleteAgent(jokerAgent.Name);
