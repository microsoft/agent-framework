// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;

internal sealed class OpenAIBasics
{
    private static async Task Main(string[] args)
    {
        Console.ForegroundColor = ConsoleColor.Gray;

        var apiKey = new ConfigurationBuilder().AddUserSecrets<OpenAIBasics>().Build()["OpenAI:ApiKey"]!;
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
        }

        async Task AFAgent()
        {
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("\n=== AF Agent ===\n");

            var agent = new OpenAIClient(apiKey).GetChatClient(modelId)
                .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes.");

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
        }
    }
}
