// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a multi-agent workflow with Writer and Reviewer agents
// using Microsoft Foundry AIProjectClient and the Agent Framework WorkflowBuilder.

#pragma warning disable CA2252 // AIProjectClient and Agents API require opting into preview features

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

Console.WriteLine($"Using Azure AI endpoint: {endpoint}");
Console.WriteLine($"Using model deployment: {deploymentName}");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create Foundry agents
AIAgent writerAgent = await aiProjectClient.CreateAIAgentAsync(
    name: "Writer",
    model: deploymentName,
    instructions: "You are an excellent content writer. You create new content and edit contents based on the feedback.");

AIAgent reviewerAgent = await aiProjectClient.CreateAIAgentAsync(
    name: "Reviewer",
    model: deploymentName,
    instructions: "You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content. Provide the feedback in the most concise manner possible.");

try
{
    var workflow = new WorkflowBuilder(writerAgent)
        .AddEdge(writerAgent, reviewerAgent)
        .Build();

    Console.WriteLine("Starting Writer-Reviewer Workflow Agent Server on http://localhost:8088");
    await workflow.AsAIAgent().RunAIAgentAsync();
}
finally
{
    // Cleanup server-side agents
    await aiProjectClient.Agents.DeleteAgentAsync(writerAgent.Name);
    await aiProjectClient.Agents.DeleteAgentAsync(reviewerAgent.Name);
}
