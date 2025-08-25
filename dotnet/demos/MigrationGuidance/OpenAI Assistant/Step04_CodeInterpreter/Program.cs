// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.OpenAI;
using OpenAI;
using OpenAI.Assistants;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

Console.ForegroundColor = ConsoleColor.Gray;

var apiKey = new ConfigurationBuilder().AddUserSecrets<Program>().Build()["OpenAI:ApiKey"]!;
var modelId = "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

var assistantsClient = new AssistantClient(apiKey);

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== SK Agent ===\n");

    var builder = Kernel.CreateBuilder().AddOpenAIChatClient(modelId, apiKey);

    // Define the assistant
    Console.Write("Creating agent in the cloud...");
    Assistant assistant = await assistantsClient.CreateAssistantAsync(modelId, enableCodeInterpreter: true);
    Console.Write("Done\n");

    // Create the agent
    OpenAIAssistantAgent agent = new(assistant, assistantsClient);

    // Create a thread for the agent conversation.
    var thread = new OpenAIAssistantAgentThread(assistantsClient);

    // Respond to user input
    Console.WriteLine("Non-Streaming Response:");
    var result = await agent.InvokeAsync(userInput, thread).FirstAsync();
    Console.WriteLine(result.Message);

    Console.WriteLine("\nStreaming Response:");
    await foreach (var update in agent.InvokeStreamingAsync(userInput, thread))
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

    Console.Write("Creating agent in the cloud...");
    var agent = await assistantsClient.CreateAIAgentAsync(modelId, tools: [new HostedCodeInterpreterTool()]);
    Console.Write("Done\n");

    var thread = agent.GetNewThread();

    Console.WriteLine("Non-Streaming Response:");
    var result = await agent.RunAsync(userInput, thread);
    Console.WriteLine(result);

    Console.WriteLine("\nStreaming Response:");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await assistantsClient.DeleteThreadAsync(thread.ConversationId);
    await assistantsClient.DeleteAssistantAsync(agent.Id);
}
