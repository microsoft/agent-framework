// Copyright (c) Microsoft. All rights reserved.

// Translation Chain Workflow Agent — demonstrates how to compose multiple AI agents
// into a sequential workflow pipeline. Three translation agents are connected:
// English → French → Spanish → English, showing how agents can be orchestrated
// as workflow executors in a hosted agent.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// Create a chat client from the Foundry project
IChatClient chatClient = new AIProjectClient(new Uri(endpoint), credential)
    .GetProjectOpenAIClient()
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create translation agents
AIAgent frenchAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to French.");
AIAgent spanishAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to Spanish.");
AIAgent englishAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to English.");

// Build the sequential workflow: French → Spanish → English
AIAgent agent = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
    .Build()
    .AsAIAgent(
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-workflows");

// Host the workflow agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
