// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple server-side AI agent with AIProjectClient.Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AgentVersion jokerAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = JokerInstructions
        }));
ChatClientAgent jokerAgent = aiProjectClient.AsAIAgent(jokerAgentVersion);

// Invoke the agent with streaming support.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(jokerAgent.Name);
