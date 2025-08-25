// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.AzureAI;
using OpenAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

internal sealed class AzureAIToolCall
{
    private static async Task Main(string[] args)
    {
        Console.ForegroundColor = ConsoleColor.Gray;

        var azureEndpoint = new ConfigurationBuilder().AddUserSecrets<AzureAIToolCall>().Build()["AzureAI:Endpoint"]!;

        var modelId = "gpt-4.1";
        var userInput = "What is the special soup and its price?";

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
            PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(
                modelId,
                name: "GenerateStory",
                instructions: "You are good at telling jokes.");
            Console.Write("Done\n");

            AzureAIAgent agent = new(definition, azureAgentClient)
            {
                Kernel = Kernel.CreateBuilder().Build(),
                Name = "Host",
                Instructions = "Answer questions about the menu",
                Arguments = new KernelArguments(new PromptExecutionSettings() { FunctionChoiceBehavior = FunctionChoiceBehavior.Auto() }),
            };

            var thread = new AzureAIAgentThread(azureAgentClient);

            // Initialize plugin and add to the agent's Kernel (same as direct Kernel usage).
            agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<MenuPlugin>());

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
            await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
        }

        async Task AFAgent()
        {
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("\n=== AF Agent ===\n");

            var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential());

            Console.Write("Creating agent in the cloud...");
            var agent = await azureAgentClient.CreateAIAgentAsync(
                modelId,
                name: "Host",
                instructions: "Answer questions about the menu");

            Console.Write("Done\n");

            var thread = agent.GetNewThread();
            var agentOptions = new ChatClientAgentRunOptions(new()
            {
                MaxOutputTokens = 1000,
                Tools = [
                    AIFunctionFactory.Create(MenuTools.GetMenu),
            AIFunctionFactory.Create(MenuTools.GetSpecials),
            AIFunctionFactory.Create(MenuTools.GetItemPrice)
                ]
            });

            Console.WriteLine("Non-Streaming Response:");
            var result = await agent.RunAsync(userInput, thread, agentOptions);
            Console.WriteLine(result);

            Console.WriteLine("\nStreaming Response:");
            await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
            {
                Console.Write(update);
            }

            // Clean up
            await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
            await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
        }
    }

    public class MenuTools
    {
        [Description("Get the full menu items.")]
        public static MenuItem[] GetMenu()
        {
            return s_menuItems;
        }

        [Description("Get the specials from the menu.")]
        public static IEnumerable<MenuItem> GetSpecials()
        {
            return s_menuItems.Where(i => i.IsSpecial);
        }

        [Description("Get the price of a menu item.")]
        public static float? GetItemPrice([Description("The name of the menu item.")] string menuItem)
        {
            return s_menuItems.FirstOrDefault(i => i.Name.Equals(menuItem, StringComparison.OrdinalIgnoreCase))?.Price;
        }

        private static readonly MenuItem[] s_menuItems = [
            new() { Category = "Soup", Name = "Clam Chowder", Price = 4.95f, IsSpecial = true },
            new() { Category = "Soup", Name = "Tomato Soup", Price = 4.95f, IsSpecial = false },
            new() { Category = "Salad", Name = "Cobb Salad", Price = 9.99f },
            new() { Category = "Salad", Name = "House Salad", Price = 4.95f },
            new() { Category = "Drink", Name = "Chai Tea", Price = 2.95f, IsSpecial = true },
            new() { Category = "Drink", Name = "Soda", Price = 1.95f },
        ];

        public sealed class MenuItem
        {
            public string Category { get; set; } = string.Empty;
            public string Name { get; set; } = string.Empty;
            public float Price { get; set; }
            public bool IsSpecial { get; set; }
        }
    }

    /// <summary>
    /// This SK Plugin wrapper is necessary as Semantic Kernel plugin functions exposed as tools require KernelFunction attributes.
    /// </summary>
    public sealed class MenuPlugin : MenuTools
    {
        [KernelFunction]
        [Description("Get the full menu items.")]
        public new static MenuItem[] GetMenu()
            => MenuTools.GetMenu();

        [KernelFunction]
        [Description("Get the specials from the menu.")]
        public new static IEnumerable<MenuItem> GetSpecials()
            => MenuTools.GetSpecials();

        [KernelFunction]
        [Description("Get the price of a menu item.")]
        public new static float? GetItemPrice([Description("The name of the menu item.")] string menuItem)
            => MenuTools.GetItemPrice(menuItem);
    }
}
