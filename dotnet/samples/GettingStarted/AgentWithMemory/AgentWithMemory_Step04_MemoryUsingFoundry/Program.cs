// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the FoundryMemoryProvider to persist and recall memories for an agent.
// The sample stores conversation messages in an Azure AI Foundry memory store and retrieves relevant
// memories for subsequent invocations, even across new sessions.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.FoundryMemory;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

string openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

string foundryEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string memoryStoreName = Environment.GetEnvironmentVariable("FOUNDRY_MEMORY_STORE_NAME") ?? throw new InvalidOperationException("FOUNDRY_MEMORY_STORE_NAME is not set.");

// Create an AIProjectClient for Foundry Memory with Azure Identity authentication.
AzureCliCredential credential = new();
AIProjectClient projectClient = new(new Uri(foundryEndpoint), credential);

AIAgent agent = new AzureOpenAIClient(new Uri(openAiEndpoint), credential)
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { Instructions = "You are a friendly travel assistant. Use known memories about the user when responding, and do not invent details." },
        AIContextProviderFactory = (ctx, ct) => new ValueTask<AIContextProvider>(ctx.SerializedState.ValueKind is not JsonValueKind.Null and not JsonValueKind.Undefined
            // If each session should have its own scope, you can create a new id per session here:
            // ? new FoundryMemoryProvider(projectClient, new FoundryMemoryProviderScope() { Scope = Guid.NewGuid().ToString() }, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName })
            // In this case we are storing memories scoped by user so that memories are retained across sessions.
            ? new FoundryMemoryProvider(projectClient, new FoundryMemoryProviderScope() { Scope = "sample-user-123" }, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName })
            // For cases where we are restoring from serialized state:
            : new FoundryMemoryProvider(projectClient, ctx.SerializedState, ctx.JsonSerializerOptions, new FoundryMemoryProviderOptions() { MemoryStoreName = memoryStoreName }))
    });

AgentSession session = await agent.GetNewSessionAsync();

// Clear any existing memories for this scope to demonstrate fresh behavior.
FoundryMemoryProvider memoryProvider = session.GetService<FoundryMemoryProvider>()!;
await memoryProvider.ClearStoredMemoriesAsync();

Console.WriteLine(await agent.RunAsync("Hi there! My name is Taylor and I'm planning a hiking trip to Patagonia in November.", session));
Console.WriteLine(await agent.RunAsync("I'm travelling with my sister and we love finding scenic viewpoints.", session));

Console.WriteLine("\nWaiting briefly for Foundry Memory to index the new memories...\n");
await Task.Delay(TimeSpan.FromSeconds(3));

Console.WriteLine(await agent.RunAsync("What do you already know about my upcoming trip?", session));

Console.WriteLine("\n>> Serialize and deserialize the session to demonstrate persisted state\n");
JsonElement serializedSession = session.Serialize();
AgentSession restoredSession = await agent.DeserializeSessionAsync(serializedSession);
Console.WriteLine(await agent.RunAsync("Can you recap the personal details you remember?", restoredSession));

Console.WriteLine("\n>> Start a new session that shares the same Foundry Memory scope\n");
AgentSession newSession = await agent.GetNewSessionAsync();
Console.WriteLine(await agent.RunAsync("Summarize what you already know about me.", newSession));
