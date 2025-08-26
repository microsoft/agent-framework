// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.AzureAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

Console.ForegroundColor = ConsoleColor.Gray;

var azureEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var modelId = "gpt-4.1";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== SK Agent ===\n");

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddSingleton((sp) => AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential()));
    serviceCollection.AddTransient<AzureAIAgent>((sp) =>
    {
        var azureAgentClient = sp.GetRequiredService<PersistentAgentsClient>();

        Console.Write("Creating agent in the cloud...");

        PersistentAgent definition = azureAgentClient.Administration
            .CreateAgentAsync(modelId,
                name: "GenerateStory",
                instructions: "You are good at telling jokes.")
            .GetAwaiter()
            .GetResult();

        Console.Write("Done\n");

        return new(definition, azureAgentClient);
    });
    serviceCollection.AddKernel();

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<AzureAIAgent>();

    var thread = new AzureAIAgentThread(agent.Client);

    Console.WriteLine("Non-Streaming Response:");
    Console.WriteLine("Waiting agent output...");
    var result = await agent.InvokeAsync(userInput).FirstAsync();
    Console.WriteLine(result.Message);

    Console.WriteLine("\nStreaming Response:");
    Console.WriteLine("Waiting agent output...");
    await foreach (ChatMessageContent update in agent.InvokeAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await thread.DeleteAsync();
    await agent.Client.Administration.DeleteAgentAsync(agent.Id);
}

async Task AFAgent()
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("\n=== AF Agent ===\n");

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddSingleton((sp) => AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential()));
    serviceCollection.AddTransient<AIAgent>((sp) =>
    {
        var azureAgentClient = sp.GetRequiredService<PersistentAgentsClient>();

        Console.Write("Creating agent in the cloud...");

        var aiAgent = azureAgentClient.CreateAIAgentAsync(
            modelId,
            name: "GenerateStory",
            instructions: "You are good at telling jokes.")
            .GetAwaiter()
            .GetResult();

        Console.Write("Done\n");

        return aiAgent;
    });

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<AIAgent>();

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
    var azureAgentClient = serviceProvider.GetRequiredService<PersistentAgentsClient>();
    await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}
