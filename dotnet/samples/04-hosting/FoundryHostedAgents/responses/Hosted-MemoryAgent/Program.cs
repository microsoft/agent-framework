// Copyright (c) Microsoft. All rights reserved.

// Hosted-MemoryAgent
//
// Demonstrates how to host an agent that uses FoundryMemoryProvider so that user-private memories
// persist across requests and across sessions, scoped per user via the Foundry platform's
// isolation key headers.
//
// Memory scope flows from request -> hosting layer -> session -> provider:
//   1. Foundry sets x-agent-user-id on every inbound request.
//   2. AgentFrameworkResponseHandler reads context.PlatformContext.UserIdKey via the registered
//      HostedSessionIsolationKeyProvider and stores it on the session as a HostedSessionContext.
//   3. FoundryMemoryProvider's stateInitializer reads HostedSessionContext.UserId and uses it as
//      the FoundryMemoryProviderScope, partitioning memories per user.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development).
Env.TraversePath().Load();

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var agentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AGENT_NAME"),
    "hosted-memory-agent")!;
var deployment = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o")!;
var embeddingDeployment = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME"),
    "text-embedding-ada-002")!;
var memoryStoreName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID"),
    "hosted-memory-sample")!;

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in foundry).
var credential = new DefaultAzureCredential();

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
//
// Per-user memory isolation comes from the platform-injected x-agent-user-id header, resolved by the
// default HostedSessionIsolationKeyProvider into the session's HostedSessionContext. This sample scopes
// memory per user via HostedFoundryMemoryProviderScopes.PerUser(), which REQUIRES that context: a
// request with no resolved user identity throws. So locally you must send an x-agent-user-id request
// header (see scripts/smoke.ps1); vary it to simulate distinct users. On the Foundry platform the
// header is always present, so no local provider registration is needed.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();


app.Run();

static string? FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate));
