// Copyright (c) Microsoft. All rights reserved.

// Step 1: Your First Agent
// The simplest possible agent — send a message, get a response.
// Uses Azure AI Foundry Responses API as the default provider.
//
// For more on agents, see: ../02-agents/README.md
// For docs: https://learn.microsoft.com/agent-framework/get-started/your-first-agent

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

// <create_agent>
string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "Assistant",
    model: deploymentName,
    instructions: "You are a helpful assistant.");
// </create_agent>

// <run_agent>
Console.WriteLine(await agent.RunAsync("What is the capital of France?"));
// </run_agent>

// <run_agent_streaming>
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me a fun fact about Paris."))
{
    Console.Write(update);
}
Console.WriteLine();
// </run_agent_streaming>

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
