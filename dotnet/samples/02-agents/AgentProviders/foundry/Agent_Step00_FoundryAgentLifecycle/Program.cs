// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create, use, and clean up a FoundryAgent backed by a server-side
// versioned agent in Microsoft Foundry. It demonstrates the full lifecycle:
// create agent version -> wrap as FoundryAgent -> run -> delete.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI.Foundry;

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

const string JokerName = "JokerAgent";

// Create the AIProjectClient to manage server-side agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a server-side agent version using the native SDK.
ProjectsAgentVersion agentVersion = await aiProjectClient.AgentAdministrationClient.CreateAgentVersionAsync(
    JokerName,
    new ProjectsAgentVersionCreationOptions(
        new DeclarativeAgentDefinition(model: deploymentName)
        {
            Instructions = "You are good at telling jokes.",
        }));

// Wrap the agent version as a FoundryAgent using the AsAIAgent extension.
FoundryAgent agent = aiProjectClient.AsAIAgent(agentVersion);

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.AgentAdministrationClient.DeleteAgentAsync(agent.Name);
