// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using OpenAI;

internal sealed class OpenAIDependencyInjection
{
    private static async Task Main(string[] args)
    {
        Console.ForegroundColor = ConsoleColor.Gray;

        var apiKey = new ConfigurationBuilder().AddUserSecrets<OpenAIDependencyInjection>().Build()["OpenAI:ApiKey"]!;
        var modelId = "gpt-4o";
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
            serviceCollection.AddKernel().AddOpenAIChatClient(modelId, apiKey);
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

        async Task AFAgent()
        {
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("\n=== AF Agent ===\n");

            var serviceCollection = new ServiceCollection();
            serviceCollection.AddTransient((sp) => new OpenAIClient(apiKey)
                .GetChatClient(modelId)
                .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes."));

            await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
            var agent = serviceProvider.GetRequiredService<AIAgent>();

            var result = await agent.RunAsync(userInput);
            Console.WriteLine(result);
        }
    }
}
