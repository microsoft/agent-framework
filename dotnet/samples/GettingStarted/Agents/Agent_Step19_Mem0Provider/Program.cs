// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the Mem0Provider to persist and recall memories for an agent.
// The sample stores conversation messages in a Mem0 service and retrieves relevant memories
// for subsequent invocations, even across new threads.

using System.Net.Http.Headers;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Mem0;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

var mem0ServiceUri = Environment.GetEnvironmentVariable("MEM0_ENDPOINT") ?? throw new InvalidOperationException("MEM0_ENDPOINT is not set.");
var mem0ApiKey = Environment.GetEnvironmentVariable("MEM0_APIKEY") ?? throw new InvalidOperationException("MEM0_APIKEY is not set.");

// Create an HttpClient for Mem0 with the required base address and authentication.
using HttpClient mem0HttpClient = new();
mem0HttpClient.BaseAddress = new Uri(mem0ServiceUri);
mem0HttpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", mem0ApiKey);

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions()
    {
        Instructions = "You are a friendly travel assistant. Use known memories about the user when responding, and do not invent details.",
        AIContextProviderFactory = ctx => ctx.SerializedState.ValueKind is not JsonValueKind.Null or JsonValueKind.Undefined
            // If each thread should have its own Mem0 scope, you can create a new id per thread here:
            // ? new Mem0Provider(mem0HttpClient, new Mem0ProviderScope() { ThreadId = Guid.NewGuid().ToString() })
            // In this case we are storing memories scoped by application and user instead so that memories are retained across threads.
            ? new Mem0Provider(mem0HttpClient, new Mem0ProviderScope() { ApplicationId = "getting-started-agents", UserId = "sample-user" })
            // For cases where we are restoring from serialized state:
            : new Mem0Provider(mem0HttpClient, ctx.SerializedState, ctx.JsonSerializerOptions)
    });

AgentThread thread = agent.GetNewThread();

// Clear any existing memories for this scope to demonstrate fresh behavior.
Mem0Provider mem0Provider = thread.GetService<Mem0Provider>()!;
await mem0Provider.ClearStoredMemoriesAsync();

Console.WriteLine(await agent.RunAsync("Hi there! My name is Taylor and I'm planning a hiking trip to Patagonia in November.", thread));
Console.WriteLine(await agent.RunAsync("I'm travelling with my sister and we love finding scenic viewpoints.", thread));

Console.WriteLine("\nWaiting briefly for Mem0 to index the new memories...\n");
await Task.Delay(TimeSpan.FromSeconds(2));

Console.WriteLine(await agent.RunAsync("What do you already know about my upcoming trip?", thread));

Console.WriteLine("\n>> Serialize and deserialize the thread to demonstrate persisted state\n");
JsonElement serializedThread = thread.Serialize();
AgentThread restoredThread = agent.DeserializeThread(serializedThread);
Console.WriteLine(await agent.RunAsync("Can you recap the personal details you remember?", restoredThread));

Console.WriteLine("\n>> Start a new thread that shares the same Mem0 scope\n");
AgentThread newThread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Summarize what you already know about me.", newThread));
