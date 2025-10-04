// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
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

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddKernel().AddGoogleAIGeminiChatCompletion(model, apiKey);
    serviceCollection.AddTransient((sp) => new ChatCompletionAgent()
    {
        Kernel = sp.GetRequiredService<Kernel>(),
        Name = "Joker",
        Instructions = "You are good at telling jokes."
    });

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<ChatCompletionAgent>();

    var result = await agent.InvokeAsync(userInput).FirstAsync();
    Console.WriteLine(result.Message);
}

async Task AFAgentAsync()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    var serviceCollection = new ServiceCollection();
    serviceCollection.AddTransient<AIAgent>((sp)
        => new ChatClientAgent(
            // Create the agent with SK's Google Gemini Chat Completion service converted to a chat client
            chatClient: new GoogleAIGeminiChatCompletionService(model, apiKey).AsChatClient(),
            name: "Joker",
            instructions: "You are good at telling jokes."));

    await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
    var agent = serviceProvider.GetRequiredService<AIAgent>();

    var result = await agent.RunAsync(userInput);
    Console.WriteLine(result);
}
