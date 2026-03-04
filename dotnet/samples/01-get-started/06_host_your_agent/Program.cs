// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to host an AI agent with Azure Functions (DurableAgents).
//
// Prerequisites:
//   - Azure Functions Core Tools
//   - Azure AI Foundry project
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT
//   AZURE_AI_MODEL_DEPLOYMENT_NAME (defaults to "gpt-4o-mini")
//
// Run with: func start
// Then call: POST http://localhost:7071/api/agents/HostedAgent/run

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <create_agent>
// Set up an AI agent following the standard Microsoft Agent Framework pattern.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient();

ChatClientAgent agent = new(chatClient, new ChatClientAgentOptions
{
    Name = "HostedAgent",
    ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a helpful assistant hosted in Azure Functions." },
});
// </create_agent>

// <host_agent>
// Configure the function app to host the AI agent.
// This will automatically generate HTTP API endpoints for the agent.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .Build();
app.Run();
// </host_agent>
