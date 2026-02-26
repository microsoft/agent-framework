// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create an Azure AI Foundry Agent with the Deep Research Tool.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deepResearchDeploymentName = Environment.GetEnvironmentVariable("AZURE_AI_REASONING_DEPLOYMENT_NAME") ?? "o3-deep-research";
var modelDeploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";
var bingConnectionId = Environment.GetEnvironmentVariable("AZURE_AI_BING_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_AI_BING_CONNECTION_ID is not set.");

// Configure extended network timeout for long-running Deep Research tasks.
PersistentAgentsAdministrationClientOptions persistentAgentsClientOptions = new();
persistentAgentsClientOptions.Retry.NetworkTimeout = TimeSpan.FromMinutes(20);

// Get a client to create/retrieve server side agents with.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
PersistentAgentsClient persistentAgentsClient = new(endpoint, new DefaultAzureCredential(), persistentAgentsClientOptions);

// Define and configure the Deep Research tool.
DeepResearchToolDefinition deepResearchTool = new(new DeepResearchDetails(
    bingGroundingConnections: [new(bingConnectionId)],
    model: deepResearchDeploymentName)
 );

// Create an agent with the Deep Research tool on the Azure AI agent service.
AIAgent agent = await persistentAgentsClient.CreateAIAgentAsync(
    model: modelDeploymentName,
    name: "DeepResearchAgent",
    instructions: "You are a helpful Agent that assists in researching scientific topics.",
    tools: [deepResearchTool]);

const string Task = "Research the current state of studies on orca intelligence and orca language, " +
    "including what is currently known about orcas' cognitive capabilities and communication systems.";

Console.WriteLine($"# User: '{Task}'");
Console.WriteLine();

try
{
    AgentSession session = await agent.CreateSessionAsync();

    await foreach (var response in agent.RunStreamingAsync(Task, session))
    {
        Console.Write(response.Text);
    }
}
finally
{
    await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
}
