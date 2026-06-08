// Copyright (c) Microsoft. All rights reserved.

// Hosted-MemoryAgent
//
// Demonstrates how to host an agent that uses FoundryMemoryProvider so that user-private memories
// persist across requests and across sessions, scoped per user via the Foundry platform's
// isolation key headers.
//
// Memory scope flows from request -> hosting layer -> session -> provider:
//   1. Foundry sets x-agent-user-isolation-key on every inbound request.
//   2. AgentFrameworkResponseHandler reads context.Isolation.UserIsolationKey via the registered
//      HostedSessionIsolationKeyProvider and stores it on the session as a HostedSessionContext.
//   3. FoundryMemoryProvider's stateInitializer reads HostedSessionContext.UserId and uses it as
//      the FoundryMemoryProviderScope, partitioning memories per user.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development).
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set."));
var agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("AGENT_NAME is not set.");
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";
var embeddingDeployment = Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-ada-002";
var memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? "hosted-memory-sample";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in foundry).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

AIProjectClient projectClient = new(projectEndpoint, credential);

// FoundryMemoryProvider partitions memories per end user via a built-in HostedFoundryMemoryProviderScopes
// helper that reads the platform-injected user isolation key from the HostedSessionContext that the
// hosting layer placed on the session.
FoundryMemoryProvider memoryProvider = new(
    projectClient,
    memoryStoreName,
    stateInitializer: HostedFoundryMemoryProviderScopes.PerUser());

// Provision the memory store on startup if it does not already exist. EnsureMemoryStoreCreatedAsync
// is idempotent. Doing this once at start avoids per-request latency.
await memoryProvider.EnsureMemoryStoreCreatedAsync(deployment, embeddingDeployment, "Memory store for the hosted travel-assistant sample.");

const string AgentInstructions = """
    You are a friendly travel assistant. When the user shares trip preferences, destinations,
    travel companions, or constraints, remember them and use them in later turns. Use known
    memories about the user when responding, and do not invent details.
    """;

ChatClientAgent agent = projectClient.AsAIAgent(new ChatClientAgentOptions()
{
    Name = agentName,
    ChatOptions = new ChatOptions
    {
        ModelId = deployment,
        Instructions = AgentInstructions
    },
    AIContextProviders = [memoryProvider]
});

// Host the agent as a Foundry Hosted Agent using the Responses API.
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
