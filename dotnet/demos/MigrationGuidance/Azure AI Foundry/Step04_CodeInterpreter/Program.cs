// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.AzureAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

Console.ForegroundColor = ConsoleColor.Gray;

var azureEndpoint = new ConfigurationBuilder().AddUserSecrets<Program>().Build()["AzureAI:Endpoint"]!;
var modelId = "gpt-4.1";
var userInput = "Use code to determine the values in the Fibonacci sequence that that are less then the value of 101?";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== SK Agent ===\n");

    var azureAgentClient = AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(modelId, tools: [new CodeInterpreterToolDefinition()]);
    Console.Write("Done\n");

    AzureAIAgent agent = new(definition, azureAgentClient);
    var thread = new AzureAIAgentThread(azureAgentClient);

    Console.WriteLine("Non-Streaming Response:");
    Console.WriteLine("Waiting agent output...");
    var result = await agent.InvokeAsync(userInput, thread).FirstAsync();
    Console.WriteLine(result.Message);

    Console.WriteLine("\nStreaming Response:");
    Console.WriteLine("Waiting agent output...");
    await foreach (ChatMessageContent update in agent.InvokeAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await thread.DeleteAsync();
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}

async Task AFAgent()
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("\n=== AF Agent ===\n");

    var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    var agent = await azureAgentClient.CreateAIAgentAsync(modelId, tools: [new CodeInterpreterToolDefinition()]);
    Console.Write("Done\n");

    var thread = agent.GetNewThread();

    Console.WriteLine("Non-Streaming Response:");
    Console.WriteLine("Waiting agent output...");
    var result = await agent.RunAsync(userInput, thread);
    Console.WriteLine(result);

    Console.WriteLine("\nStreaming Response:");
    Console.WriteLine("Waiting agent output...");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}
