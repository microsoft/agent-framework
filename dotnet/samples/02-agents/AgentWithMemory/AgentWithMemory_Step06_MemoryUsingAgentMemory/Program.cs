// Copyright (c) Microsoft. All rights reserved.

// Agent Memory — Shopping Assistant (Microsoft Agent Framework, .NET)
//
// A .NET port of the Neo4j Labs "agent-memory" retail-assistant example
// (https://github.com/neo4j-labs/agent-memory/tree/main/examples/microsoft_agent_retail_assistant,
// referenced from https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-memory).
//
// A shopping assistant that LEARNS a customer's preferences and RECOMMENDS products via graph
// traversal, backed by DURABLE memory in Neo4j. It uses the AgentMemory library — a .NET port of the
// Python memory provider, not an officially recognized Neo4j integration — and its Microsoft Agent
// Framework adapter:
//   • Neo4jMemoryContextProvider  (an AIContextProvider)  — recalls memory before each run, persists after
//   • MemoryToolFactory.CreateAIFunctions()               — memory tools (search/remember/recall)
//   • ProductCatalog.CreateAIFunctions()                  — retail tools over a Neo4j :Product graph
//
// This is a STANDALONE sample consuming the published AgentMemory NuGet packages.
//
// Configuration (environment variables, matching the other Foundry samples):
//   AZURE_OPENAI_ENDPOINT     (required)  — your Azure OpenAI / Foundry endpoint
//   AZURE_OPENAI_API_KEY      (optional)  — API key; if unset, DefaultAzureCredential (az login) is used
//   FOUNDRY_MODEL             (default: gpt-4o-mini)            — chat model deployment
//   FOUNDRY_EMBEDDING_MODEL   (default: text-embedding-3-small) — embedding model deployment (1536 dims)
//   NEO4J_URI                 (default: bolt://localhost:7687)
//   NEO4J_USER                (default: neo4j)
//   NEO4J_PASSWORD            (default: password)

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI;
using AgentMemory.Abstractions.Services;
using AgentMemory.AgentFramework;
using AgentMemory.AgentFramework.Tools;
using AgentMemory.Core;
using AgentMemory.Core.Stubs;
using AgentMemory.Neo4j.Infrastructure;
using AgentMemoryShoppingAssistant;

// ── Model + credentials (Azure OpenAI / Foundry, via env vars) ───────────────────────────────────
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var apiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
var chatModel = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o-mini";
var embeddingModel = Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_MODEL") ?? "text-embedding-3-small";

var clientOptions = new OpenAIClientOptions { Endpoint = new Uri(endpoint) };
// API key if provided, otherwise Azure credential (dev: `az login`).
OpenAIClient openAI = string.IsNullOrWhiteSpace(apiKey)
    ? new OpenAIClient(new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"), clientOptions)
    : new OpenAIClient(new ApiKeyCredential(apiKey), clientOptions);

IChatClient chatClient = openAI.GetChatClient(chatModel).AsIChatClient();
IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator =
    openAI.GetEmbeddingClient(embeddingModel).AsIEmbeddingGenerator();

// ── AgentMemory (Neo4j) DI ───────────────────────────────────────────────────────────────────────
var builder = Host.CreateApplicationBuilder(args);
builder.Logging.SetMinimumLevel(LogLevel.Warning);

builder.Services.AddNeo4jAgentMemory(options =>
{
    options.Uri      = Environment.GetEnvironmentVariable("NEO4J_URI")      ?? "bolt://localhost:7687";
    options.Username = Environment.GetEnvironmentVariable("NEO4J_USER")     ?? "neo4j";
    options.Password = Environment.GetEnvironmentVariable("NEO4J_PASSWORD") ?? "password";
});
builder.Services.AddAgentMemoryCore(_ => { });
builder.Services.AddSingleton<IClock, SystemClock>();
builder.Services.AddSingleton<IIdGenerator, GuidIdGenerator>();
builder.Services.TryAddSingleton(chatClient);
builder.Services.TryAddSingleton(embeddingGenerator);
builder.Services.AddAgentMemoryFramework(options =>
{
    options.AutoExtractOnPersist             = true;
    options.ContextFormat.IncludeEntities    = true;
    options.ContextFormat.IncludeFacts       = true;
    options.ContextFormat.IncludePreferences = true;
});

using var host = builder.Build();
await using var hostDisposal = (IAsyncDisposable)host;

await using var scope = host.Services.CreateAsyncScope();
var sp = scope.ServiceProvider;

// ── Setup: schema + sample product graph ─────────────────────────────────────────────────────────
var catalog = new ProductCatalog(sp.GetRequiredService<INeo4jTransactionRunner>());
await sp.GetRequiredService<ISchemaBootstrapper>().BootstrapAsync();
await catalog.SeedAsync();
Console.WriteLine("Neo4j schema ready; sample products loaded.\n");

// ── The shopping assistant: context provider + memory tools + product tools ──────────────────────
var memoryProvider = sp.GetRequiredService<Neo4jMemoryContextProvider>();
var memoryTools    = sp.GetRequiredService<MemoryToolFactory>().CreateAIFunctions();
var productTools   = catalog.CreateAIFunctions();

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "ShoppingAssistant",
    ChatOptions = new ChatOptions
    {
        ModelId = chatModel,
        Instructions =
            "You are a helpful shopping assistant for an online store. Learn and remember the customer's "
          + "preferences (brands, budget, categories) using the memory tools, and recommend products that "
          + "fit using the product tools. Explain why each recommendation matches, and suggest alternatives "
          + "when something is out of stock.",
        Tools = [.. memoryTools, .. productTools],
    },
    AIContextProviders = [memoryProvider],
});

var ownerContext = sp.GetRequiredService<IWritableMemoryOwnerContext>();
const string shopper = "shopper-amelia";

// ── Session A — the customer shops; the model calls the tools and remembers preferences ──────────
Console.WriteLine(">> Session A\n");
var sessionA = (await agent.CreateSessionAsync())
    .WithMemoryIdentity(userId: shopper, sessionId: "cart-a", applicationId: "retail-demo");

foreach (var turn in new[]
{
    "Hi! I'm looking for running shoes. I love Nike and want to stay under $150.",
    "Nice — what would you recommend for me, and is anything I might like out of stock?",
})
{
    await SayAsync(agent, sessionA, ownerContext, shopper, turn);
}

// ── Session B — a NEW session for the same shopper still recalls her preferences ─────────────────
Console.WriteLine(">> Session B — a brand-new session; memory is durable\n");
var sessionB = (await agent.CreateSessionAsync())
    .WithMemoryIdentity(userId: shopper, sessionId: "cart-b", applicationId: "retail-demo");

await SayAsync(agent, sessionB, ownerContext, shopper, "I'm back — remind me what I like and suggest something new.");

Console.WriteLine("=== Done. Preferences + messages persist in Neo4j across sessions. ===");

// One conversational turn. The ambient owner scope keeps any model-invoked memory tools scoped to
// this shopper. The context provider recalls memory before the run and persists after — automatically.
static async Task SayAsync(AIAgent agent, AgentSession session, IWritableMemoryOwnerContext ownerContext,
    string userId, string message)
{
    Console.WriteLine($"USER      : {message}");
    using (ownerContext.BeginOwnerScope(userId))
    {
        var response = await agent.RunAsync(message, session);
        Console.WriteLine($"ASSISTANT : {response.Text}\n");
    }
}
