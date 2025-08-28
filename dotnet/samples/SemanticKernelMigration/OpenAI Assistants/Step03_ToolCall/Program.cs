// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

using System.ComponentModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.OpenAI;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;
using OpenAI.Assistants;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var modelId = Environment.GetEnvironmentVariable("OPENAI_MODELID") ?? "gpt-4o";
var userInput = "What is the special soup and its price?";

Console.WriteLine($"User Input: {userInput}");

await SKAgent();
await AFAgent();

async Task SKAgent()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var builder = Kernel.CreateBuilder();
    var assistantsClient = new AssistantClient(apiKey);

    // Define the assistant with function calling enabled
    Console.Write("Creating agent in the cloud...");
    Assistant assistant = await assistantsClient.CreateAssistantAsync(
        modelId,
        name: "Host",
        instructions: "Answer questions about the menu");
    Console.Write("Done\n");

    // Create the agent
    OpenAIAssistantAgent agent = new(assistant, assistantsClient)
    {
        Kernel = builder.Build(),
        Arguments = new KernelArguments(new OpenAIPromptExecutionSettings()
        {
            MaxTokens = 1000,
            FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
        }),
    };

    // Initialize plugin and add to the agent's Kernel (same as direct Kernel usage).
    agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<MenuPlugin>());

    // Create a thread for the agent conversation.
    var thread = new OpenAIAssistantAgentThread(assistantsClient);

    Console.WriteLine("Non-Streaming Response:");
    await foreach (var result in agent.InvokeAsync(userInput, thread))
    {
        Console.WriteLine(result.Message);
    }

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
    Console.WriteLine("\n=== AF Agent ===\n");

    var assistantClient = new AssistantClient(apiKey);

    Console.Write("Creating agent in the cloud...");
    var agent = await assistantClient.CreateAIAgentAsync(
        modelId,
        name: "Host",
        instructions: "Answer questions about the menu",
        tools: [
            AIFunctionFactory.Create(MenuTools.GetMenu),
            AIFunctionFactory.Create(MenuTools.GetSpecials),
            AIFunctionFactory.Create(MenuTools.GetItemPrice)
        ]);
    Console.Write("Done\n");

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
    await assistantClient.DeleteThreadAsync(thread.ConversationId);
    await assistantClient.DeleteAssistantAsync(agent.Id);
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
