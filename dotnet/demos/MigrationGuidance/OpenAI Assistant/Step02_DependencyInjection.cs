// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.OpenAI;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;
using OpenAI.Assistants;

Console.ForegroundColor = ConsoleColor.Gray;

var apiKey = new ConfigurationBuilder().AddUserSecrets<Program>().Build()["OpenAI:ApiKey"]!;
var modelId = "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine($"\n=== SK Agent ===\n");

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddSingleton((sp) => new AssistantClient(apiKey));
    serviceCollection.AddKernel().AddOpenAIChatClient(modelId, apiKey);
    serviceCollection.AddTransient((sp) =>
    {
        var assistantsClient = sp.GetRequiredService<AssistantClient>();

        Console.Write("Creating agent in the cloud...");
        Assistant assistant = assistantsClient.CreateAssistantAsync(modelId, name: "Joker", instructions: "You are good at telling jokes.")
            .GetAwaiter()
            .GetResult();
        Console.Write("Done\n");

        return new OpenAIAssistantAgent(assistant, assistantsClient);
    });

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<OpenAIAssistantAgent>();

    // Create a thread for the agent conversation.
    var assistantsClient = serviceProvider.GetRequiredService<AssistantClient>();
    var thread = new OpenAIAssistantAgentThread(assistantsClient);
    var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
    var agentOptions = new OpenAIAssistantAgentInvokeOptions() { KernelArguments = new(settings) };

    Console.WriteLine("Non-Streaming Response:");
    await foreach (var result in agent.InvokeAsync(userInput, thread, agentOptions))
    {
        Console.WriteLine(result.Message);
    }

    Console.WriteLine("\nStreaming Response:");
    await foreach (var update in agent.InvokeStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update.Message);
    }

    // Clean up
    await thread.DeleteAsync();
    await assistantsClient.DeleteAssistantAsync(agent.Id);
}

async Task AFAgent() 
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("\n=== AF Agent ===\n");

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddSingleton((sp) => new AssistantClient(apiKey));
    serviceCollection.AddTransient((sp) =>
    {
        var assistantClient = sp.GetRequiredService<AssistantClient>();

        Console.Write("Creating agent in the cloud...");
        var agent = assistantClient.CreateAIAgentAsync(modelId, name: "Joker", instructions: "You are good at telling jokes.")
            .GetAwaiter()
            .GetResult();
        Console.Write("Done\n");

        return agent;
    });

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<AIAgent>();

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

    Console.WriteLine("Non-Streaming Response:");
    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("\nStreaming Response:");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }

    // Clean up
    var assistantClient = serviceProvider.GetRequiredService<AssistantClient>();
    await assistantClient.DeleteThreadAsync(thread.ConversationId);
    await assistantClient.DeleteAssistantAsync(agent.Id);
}
