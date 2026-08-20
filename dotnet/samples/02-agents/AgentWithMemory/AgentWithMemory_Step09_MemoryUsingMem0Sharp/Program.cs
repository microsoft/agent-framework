// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Mem0Sharp's in-memory store with an Agent Framework agent.

using Azure.AI.Projects;
using Azure.Identity;
using Mem0Sharp;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

var memory = new MemoryService();
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = aiProjectClient
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a helpful assistant. Use remembered preferences when relevant, and do not invent memories." },
        AIContextProviders = [new Mem0SharpProvider(memory, userId: "sample-user")],
    });

AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("I prefer window seats when I fly.", session));

Console.WriteLine("\n>> Start a new session that shares the same Mem0Sharp memory\n");
AgentSession newSession = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Which seat should I book for my next flight?", newSession));