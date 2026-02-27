// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a multi-agent workflow with Writer and Reviewer agents
// using Azure AI Foundry PersistentAgentsClient and the Agent Framework WorkflowBuilder.

using Azure.AI.Agents.Persistent;
using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.WriteLine($"Using Azure AI endpoint: {endpoint}");
Console.WriteLine($"Using model deployment: {deploymentName}");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
TokenCredential credential = string.IsNullOrEmpty(Environment.GetEnvironmentVariable("MSI_ENDPOINT"))
    ? new DefaultAzureCredential()
    : new ManagedIdentityCredential();

// Create separate PersistentAgentsClient for each agent
var writerClient = new PersistentAgentsClient(endpoint, credential);
var reviewerClient = new PersistentAgentsClient(endpoint, credential);

(ChatClientAgent agent, string id)? writer = null;
(ChatClientAgent agent, string id)? reviewer = null;

try
{
    // Create Foundry agents with separate clients
    writer = await CreateAgentAsync(
        writerClient,
        deploymentName,
        "Writer",
        "You are an excellent content writer. You create new content and edit contents based on the feedback."
    );
    reviewer = await CreateAgentAsync(
        reviewerClient,
        deploymentName,
        "Reviewer",
        "You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content. Provide the feedback in the most concise manner possible."
    );

    var workflow = new WorkflowBuilder(writer.Value.agent)
        .AddEdge(writer.Value.agent, reviewer.Value.agent)
        .WithOutputFrom(reviewer.Value.agent)
        .Build();

    Console.WriteLine("Starting Writer-Reviewer Workflow Agent Server on http://localhost:8088");
    await workflow.AsAgent().RunAIAgentAsync();
}
finally
{
    // Clean up all resources
    await CleanupAsync(writerClient, writer?.id);
    await CleanupAsync(reviewerClient, reviewer?.id);

    if (credential is IDisposable disposable)
    {
        disposable.Dispose();
    }
}

static async Task<(ChatClientAgent agent, string id)> CreateAgentAsync(
    PersistentAgentsClient client,
    string model,
    string name,
    string instructions)
{
    var agentMetadata = await client.Administration.CreateAgentAsync(
        model: model,
        name: name,
        instructions: instructions
    );

    var chatClient = client.AsIChatClient(agentMetadata.Value.Id);
    return (new ChatClientAgent(chatClient), agentMetadata.Value.Id);
}

static async Task CleanupAsync(PersistentAgentsClient client, string? agentId)
{
    if (string.IsNullOrEmpty(agentId))
    {
        return;
    }

    try
    {
        await client.Administration.DeleteAgentAsync(agentId);
    }
    catch (Exception e)
    {
        Console.WriteLine($"Cleanup failed for agent {agentId}: {e.Message}");
    }
}
