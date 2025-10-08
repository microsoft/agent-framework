// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.ChatCompletion;
using Microsoft.SemanticKernel.Connectors.Google;

var apiKey = Environment.GetEnvironmentVariable("GOOGLEAI_API_KEY") ?? throw new InvalidOperationException("GOOGLEAI_API_KEY is not set.");
var model = System.Environment.GetEnvironmentVariable("GOOGLEAI_MODEL") ?? "gemini-2.0-flash";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await SKAgentAsync();
await AFAgentAsync();

async Task SKAgentAsync()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var builder = Kernel.CreateBuilder().AddGoogleAIGeminiChatCompletion(model, apiKey);

    var agent = new ChatCompletionAgent()
    {
        Kernel = builder.Build(),
        Name = "Joker",
        Instructions = "You are good at telling jokes.",
    };

    var thread = new ChatHistoryAgentThread();
    var settings = new GeminiPromptExecutionSettings() { MaxTokens = 1000 };
    var agentOptions = new AgentInvokeOptions() { KernelArguments = new(settings) };

    await foreach (var result in agent.InvokeAsync(userInput, thread, agentOptions))
    {
        Console.WriteLine(result.Message);
    }

    Console.WriteLine("---");
    await foreach (var update in agent.InvokeStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update.Message);
    }
}

async Task AFAgentAsync()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    // Create the agent with SK's Google Gemini Chat Completion service converted to a chat client
    using var googleChatClient = new GoogleAIGeminiChatCompletionService(model, apiKey).AsChatClient();

    var agent = new ChatClientAgent(googleChatClient, name: "Joker", instructions: "You are good at telling jokes.");

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("---");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }
}
