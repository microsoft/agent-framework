// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.AzureAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

var azureEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");

var modelId = "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

async Task SKAgent()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var azureAgentClient = AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(
        modelId,
        name: "GenerateStory",
        instructions: "You are good at telling jokes.");
    Console.Write("Done\n");

    AzureAIAgent agent = new(definition, azureAgentClient);

    var thread = new AzureAIAgentThread(azureAgentClient);

    Console.WriteLine("Non-Streaming Response:");
    Console.WriteLine("Waiting agent output...");
    AzureAIAgentInvokeOptions options = new() { MaxPromptTokens = 1000 };
    var result = await agent.InvokeAsync(userInput, thread, options).FirstAsync();
    Console.WriteLine(result.Message);

    Console.WriteLine("\nStreaming Response:");
    Console.WriteLine("Waiting agent output...");
    await foreach (StreamingChatMessageContent update in agent.InvokeStreamingAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await thread.DeleteAsync();
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}

async Task AFAgent()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    var agent = await azureAgentClient.CreateAIAgentAsync(
        modelId,
        name: "GenerateStory",
        instructions: "You are good at telling jokes.");
    Console.Write("Done\n");

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

    Console.WriteLine("Non-Streaming Response:");
    Console.WriteLine("Waiting agent output...");
    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("\nStreaming Response:");
    Console.WriteLine("Waiting agent output...");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }

    // Clean up
    await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}
