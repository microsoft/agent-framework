// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Image Multi-Modality with an AI agent.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o";

const string VisionInstructions = "You are a helpful agent that can analyze images";
const string VisionName = "VisionAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var agentsClient = new AgentsClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
var agentDefinition = new PromptAgentDefinition(model: deploymentName) { Instructions = VisionInstructions };

// Create a server side agent version with the Azure.AI.Agents SDK client.
var agentVersion = agentsClient.CreateAgentVersion(agentName: VisionName, definition: agentDefinition);

// Retrieve an AIAgent for the created server side agent version.
AIAgent agent = agentsClient.GetAIAgent(agentVersion);

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),
    new UriContent("https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg", "image/jpeg")
]);

var thread = agent.GetNewThread();

await foreach (var update in agent.RunStreamingAsync(message, thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
agentsClient.DeleteAgent(agent.Name);
