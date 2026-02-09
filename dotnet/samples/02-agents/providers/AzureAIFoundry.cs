// Copyright (c) Microsoft. All rights reserved.

// Provider: Azure AI Foundry (Responses API)
// Create an agent using Azure AI Foundry Agents with AIProjectClient.
// This is the default recommended provider for Agent Framework.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <azure_ai_foundry>
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "JokerAgent",
    model: deploymentName,
    instructions: "You are good at telling jokes.");
// </azure_ai_foundry>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
