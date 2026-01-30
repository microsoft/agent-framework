// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the FoundryMemoryProvider to persist and recall memories for an agent.
// The sample stores conversation messages in an Azure AI Foundry memory store and retrieves relevant
// memories for subsequent invocations, even across new sessions.
//
// Note: Memory extraction in Azure AI Foundry is asynchronous and takes time. This sample demonstrates
// a simple polling approach to wait for memory updates to complete before querying.

using System.ClientModel.Primitives;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.FoundryMemory;

string foundryEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string memoryStoreName = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_MEMORY_STORE_NAME") ?? "sample-memory-store-name";
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_MODEL") ?? "gpt-4o-mini";
string embeddingModelName = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_EMBEDDING_MODEL") ?? "text-embedding-ada-002";

// Create an AIProjectClient for Foundry with Azure Identity authentication.
AzureCliCredential credential = new();

// Add a debug handler to log all HTTP requests
DebugHttpClientHandler debugHandler = new() { CheckCertificateRevocationList = true };
HttpClient httpClient = new(debugHandler);
AIProjectClientOptions clientOptions = new()
{
    Transport = new HttpClientPipelineTransport(httpClient)
};
AIProjectClient projectClient = new(new Uri(foundryEndpoint), credential, clientOptions);

// Get the ChatClient from the AIProjectClient's OpenAI property using the deployment name.
AIAgent agent = await projectClient.CreateAIAgentAsync(deploymentName,
    options: new ChatClientAgentOptions()
    {
        Name = "TravelAssistantWithFoundryMemory",
        ChatOptions = new() { Instructions = "You are a friendly travel assistant. Use known memories about the user when responding, and do not invent details." },
        AIContextProviderFactory = (ctx, ct) => new ValueTask<AIContextProvider>(ctx.SerializedState.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined
            // If each session should have its own scope, you can create a new id per session here:
            // ? new FoundryMemoryProvider(projectClient, new FoundryMemoryProviderScope() { Scope = Guid.NewGuid().ToString() }, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName })
            // In this case we are storing memories scoped by user so that memories are retained across sessions.
            ? new FoundryMemoryProvider(projectClient, new FoundryMemoryProviderScope() { Scope = "sample-user-123" }, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName })
            // For cases where we are restoring from serialized state:
            : new FoundryMemoryProvider(projectClient, ctx.SerializedState, ctx.JsonSerializerOptions, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName }))
    });

AgentSession session = await agent.GetNewSessionAsync();

FoundryMemoryProvider memoryProvider = session.GetService<FoundryMemoryProvider>()!;

Console.WriteLine("\n>> Setting up Foundry Memory Store\n");

// Ensure the memory store exists (creates it with the specified models if needed).
await memoryProvider.EnsureMemoryStoreCreatedAsync(deploymentName, embeddingModelName, "Sample memory store for travel assistant");

// Clear any existing memories for this scope to demonstrate fresh behavior.
await memoryProvider.EnsureStoredMemoriesDeletedAsync();

Console.WriteLine(await agent.RunAsync("Hi there! My name is Taylor and I'm planning a hiking trip to Patagonia in November.", session));
Console.WriteLine(await agent.RunAsync("I'm travelling with my sister and we love finding scenic viewpoints.", session));

// Memory extraction in Azure AI Foundry is asynchronous and takes time to process.
// WhenUpdatesCompletedAsync polls all pending updates and waits for them to complete.
Console.WriteLine("\nWaiting for Foundry Memory to process updates...");
await memoryProvider.WhenUpdatesCompletedAsync();

Console.WriteLine("Updates completed.\n");

Console.WriteLine(await agent.RunAsync("What do you already know about my upcoming trip?", session));

Console.WriteLine("\n>> Serialize and deserialize the session to demonstrate persisted state\n");
JsonElement serializedSession = session.Serialize();
AgentSession restoredSession = await agent.DeserializeSessionAsync(serializedSession);
Console.WriteLine(await agent.RunAsync("Can you recap the personal details you remember?", restoredSession));

Console.WriteLine("\n>> Start a new session that shares the same Foundry Memory scope\n");

Console.WriteLine("\nWaiting for Foundry Memory to process updates...");
await memoryProvider.WhenUpdatesCompletedAsync();

AgentSession newSession = await agent.GetNewSessionAsync();
Console.WriteLine(await agent.RunAsync("Summarize what you already know about me.", newSession));

// Debug HTTP handler to log all requests (commented out by default)
internal sealed class DebugHttpClientHandler : HttpClientHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (!request.RequestUri?.PathAndQuery.Contains("sample-memory-store-name") ?? false)
        {
            return await base.SendAsync(request, cancellationToken);
        }

        Console.WriteLine("\n=== HTTP REQUEST ===");
        Console.WriteLine($"Method: {request.Method}");
        Console.WriteLine($"URI: {request.RequestUri}");
        Console.WriteLine("Headers:");
        foreach (var header in request.Headers)
        {
            Console.WriteLine($"  {header.Key}: {string.Join(", ", header.Value)}");
        }

        if (request.Content != null)
        {
            string body = await request.Content.ReadAsStringAsync(cancellationToken);
            Console.WriteLine("Body: " + body);
        }

        HttpResponseMessage response = await base.SendAsync(request, cancellationToken);

        Console.WriteLine("====================\n");

        Console.WriteLine("\n=== HTTP RESPONSE ===");
        Console.WriteLine($"Status: {(int)response.StatusCode} {response.StatusCode}");
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        Console.WriteLine("Body: " + responseBody);
        Console.WriteLine("=====================\n");

        return response;
    }
}
