// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create, use, and clean up a FoundryAgent backed by a server-side
// versioned agent in Azure AI Foundry. It demonstrates the full lifecycle:
// create agent version -> wrap as FoundryAgent -> run -> delete.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";

// Create the AIProjectClient to manage server-side agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create a server-side agent version using the native SDK.
AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(model: deploymentName)
        {
            Instructions = "You are good at telling jokes.",
        }));

// Wrap the agent version as a FoundryAgent using the AsAIAgent extension.
FoundryAgent agent = aiProjectClient.AsAIAgent(agentVersion);

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
