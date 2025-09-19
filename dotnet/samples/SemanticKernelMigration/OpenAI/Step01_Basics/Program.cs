// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var modelId = System.Environment.GetEnvironmentVariable("OPENAI_MODELID") ?? "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await SKAgentAsync();
await AFAgentAsync();

async Task SKAgentAsync()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var builder = Kernel.CreateBuilder().AddOpenAIChatClient(modelId, apiKey);

    var agent = new ChatCompletionAgent()
    {
        Kernel = builder.Build(),
        Name = "Joker",
        Instructions = "You are good at telling jokes.",
    };

    var thread = new ChatHistoryAgentThread();
    var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
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

    var agent = new OpenAIClient(apiKey).GetChatClient(modelId)
        .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes.");

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
