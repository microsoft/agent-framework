// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Azure Foundry Agents with chat history management.
// NOTE: With Azure Foundry Agents, the service manages the chat history size server-side.
// The agent thread maintains the conversation history automatically.

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

// Create a server side agent version with the Azure.AI.Agents SDK client.
var agentVersion = agentsClient.CreateAgentVersion(agentName: JokerName, definition: agentDefinition);

// Retrieve an AIAgent for the created server side agent version.
AIAgent agent = agentsClient.GetAIAgent(agentVersion);

AgentThread thread = agent.GetNewThread();

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

// Invoke the agent a few more times.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a robot.", thread));
Console.WriteLine(await agent.RunAsync("Tell me a joke about a lemur.", thread));

// With Azure Foundry Agents, the service manages the chat history size server-side.
// The agent thread maintains the conversation history automatically.
Console.WriteLine(await agent.RunAsync("Tell me the joke about the pirate again, but add emojis and use the voice of a parrot.", thread));

// Cleanup by agent name removes the agent version created.
agentsClient.DeleteAgent(agent.Name);
