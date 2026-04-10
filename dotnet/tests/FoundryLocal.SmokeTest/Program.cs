// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.FoundryLocal;
using Microsoft.Extensions.AI;

// Quick smoke test — does FoundryLocalChatClient actually call a local model?

Console.WriteLine("=== Foundry Local Integration Test ===\n");

// 1. Create the client (this bootstraps the manager, downloads/loads the model, starts web service)
Console.WriteLine("Creating FoundryLocalChatClient with qwen2.5-0.5b...");
var client = await FoundryLocalChatClient.CreateAsync(
    new FoundryLocalClientOptions
    {
        Model = "qwen2.5-0.5b",
        PrepareModel = true,
        StartWebService = true,
    });

Console.WriteLine("  Model ID: " + client.ModelId);
Console.WriteLine("  Manager URLs: " + string.Join(", ", client.Manager.Urls ?? Array.Empty<string>()));

// 2. Create an agent
Console.WriteLine("\nCreating agent...");
var agent = client.AsAIAgent(
    instructions: "You are a helpful assistant. Keep answers very brief (1-2 sentences).",
    name: "LocalTestAgent");

Console.WriteLine("  Agent created successfully.");

// 3. Run a simple query via agent.RunAsync
Console.WriteLine("\nSending message: 'What is 2 + 2?'");
var response = await agent.RunAsync("What is 2 + 2?");

Console.WriteLine("\nResponse:");
foreach (var msg in response.Messages)
{
    Console.WriteLine("  [" + msg.Role + "]: " + msg.Text);
}

Console.WriteLine("\n=== Test Complete ===");
