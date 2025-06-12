// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Assistants;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace GettingStarted.OpenAIAssistantChatClientAgent;

public sealed class Step02_UsingTools : AgentSample, IAsyncLifetime
{
    private readonly AssistantClient _assistantClient;
    private string? _assistantId;

    public Step02_UsingTools(ITestOutputHelper output)
        : base(output)
    {
        // Get a client to create server side agents with.
        var openAIClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey);
        this._assistantClient = openAIClient.GetAssistantClient();
    }

    public async Task InitializeAsync()
    {
        // Create a server side agent to work with.
        var assistantCreateResult = await this._assistantClient.CreateAssistantAsync(
            TestConfiguration.OpenAI.ChatModelId,
            new()
            {
                Name = "Host",
                Instructions = "Answer questions about the menu.",
            });

        this._assistantId = assistantCreateResult.Value.Id;
    }

    [Fact]
    public async Task RunningWithTools()
    {
        // Get the chat client to use for the agent.
        using var chatClient = this._assistantClient.AsIChatClient(this._assistantId!);

        // Define the agent
        ChatClientAgent agent = new(chatClient);

        var menuTools = new MenuTools();
        var chatOptions = new ChatOptions
        {
            Tools = [
                AIFunctionFactory.Create(menuTools.GetMenu),
                AIFunctionFactory.Create(menuTools.GetSpecials),
                AIFunctionFactory.Create(menuTools.GetItemPrice),
            ],
        };

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await InvokeAgentAsync("Hello");
        await InvokeAgentAsync("What is the special soup and its price?");
        await InvokeAgentAsync("What is the special drink and its price?");
        await InvokeAgentAsync("Thank you");

        async Task InvokeAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            var response = await agent.RunAsync(input, thread, chatOptions: chatOptions);
            this.WriteResponseOutput(response);
        }
    }

    [Fact]
    public async Task StreamingRunWithTools()
    {
        // Get the chat client to use for the agent.
        using var chatClient = this._assistantClient.AsIChatClient(this._assistantId!);

        // Define the agent
        ChatClientAgent agent = new(chatClient);

        var menuTools = new MenuTools();
        var chatOptions = new ChatOptions
        {
            Tools = [
                AIFunctionFactory.Create(menuTools.GetMenu),
                AIFunctionFactory.Create(menuTools.GetSpecials),
                AIFunctionFactory.Create(menuTools.GetItemPrice),
            ],
        };

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await InvokeAgentAsync("Hello");
        await InvokeAgentAsync("What is the special soup and its price?");
        await InvokeAgentAsync("What is the special drink and its price?");
        await InvokeAgentAsync("Thank you");

        async Task InvokeAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            await foreach (var update in agent.RunStreamingAsync(input, thread, chatOptions: chatOptions))
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

    async Task IAsyncLifetime.DisposeAsync()
    {
        await this._assistantClient.DeleteAssistantAsync(this._assistantId);
    }
}
