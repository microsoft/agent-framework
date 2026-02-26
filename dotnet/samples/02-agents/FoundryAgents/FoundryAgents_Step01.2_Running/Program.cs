// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AgentVersionCreationOptions options = new(new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions });

// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
AgentVersion agentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options);

// You can use an AIAgent with an already created server side agent version.
AIAgent jokerAgent = aiProjectClient.AsAIAgent(agentVersion);

// Invoke the agent with streaming support.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(jokerAgent.Name);
