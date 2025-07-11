// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// This sample demonstrates how to use a <see cref="ChatClientAgent"/> with function tools.
/// It includes examples of both streaming and non-streaming agent interactions.
/// </summary>
public sealed class Step02_ChatClientAgent_UsingFunctionTools(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    public async Task RunningWithTools(ChatClientProviders provider)
    {
        // Creating a Menu Tools to be used by the agent.
        var menuTools = new MenuTools();

        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = "Host",
            Instructions = "Answer questions about the menu.",

            // Provide the tools that are available to the agent
            ChatOptions = new()
            {
                Tools = [
                    AIFunctionFactory.Create(menuTools.GetMenu),
                    AIFunctionFactory.Create(menuTools.GetSpecials),
                    AIFunctionFactory.Create(menuTools.GetItemPrice)
                ]
            },
        };

        // Get the chat client to use for the agent.
        using var chatClient = await base.GetChatClientAsync(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("Hello");
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink and its price?");
        await RunAgentAsync("Thank you");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            var response = await agent.RunAsync(input, thread);
            this.WriteResponseOutput(response);
        }
    }

    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    public async Task StreamingRunWithTools(ChatClientProviders provider)
    {
        // Creating a Menu Tools to be used by the agent.
        var menuTools = new MenuTools();

        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = "Host",
            Instructions = "Answer questions about the menu.",

            // Provide the tools that are available to the agent
            ChatOptions = new()
            {
                Tools = [
                    AIFunctionFactory.Create(menuTools.GetMenu),
                    AIFunctionFactory.Create(menuTools.GetSpecials),
                    AIFunctionFactory.Create(menuTools.GetItemPrice)
                ]
            },
        };

        // Get the chat client to use for the agent.
        using var chatClient = await base.GetChatClientAsync(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("Hello");
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink and its price?");
        await RunAgentAsync("Thank you");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            await foreach (var update in agent.RunStreamingAsync(input, thread))
            {
                this.WriteAgentOutput(update);
            }
        }
    }

    private sealed class MenuTools
    {
        [Description("Get the full menu items.")]
        public MenuItem[] GetMenu()
        {
            return s_menuItems;
        }

        [Description("Get the specials from the menu.")]
        public IEnumerable<MenuItem> GetSpecials()
        {
            return s_menuItems.Where(i => i.IsSpecial);
        }

        [Description("Get the price of a menu item.")]
        public float? GetItemPrice([Description("The name of the menu item.")] string menuItem)
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
}
