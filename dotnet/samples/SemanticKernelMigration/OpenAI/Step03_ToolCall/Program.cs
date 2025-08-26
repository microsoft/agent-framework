// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var modelId = "gpt-4o";
var userInput = "What is the special soup and its price?";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    var builder = Kernel.CreateBuilder().AddOpenAIChatClient(modelId, apiKey);

    ChatCompletionAgent agent = new()
    {
        Instructions = "Answer questions about the menu",
        Name = "Host",
        Kernel = builder.Build(),
        Arguments = new KernelArguments(new PromptExecutionSettings() { FunctionChoiceBehavior = FunctionChoiceBehavior.Auto() }),
    };

    // Initialize plugin and add to the agent's Kernel (same as direct Kernel usage).
    agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<MenuPlugin>());

    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== SK Agent Response ===\n");

    var result = await agent.InvokeAsync(userInput).FirstAsync();
    Console.WriteLine(result.Message);
}

async Task AFAgent()
{
    var agent = new OpenAIClient(apiKey).GetChatClient(modelId).CreateAIAgent(
        name: "Host",
        instructions: "Answer questions about the menu",
        tools: [
            AIFunctionFactory.Create(MenuTools.GetMenu),
            AIFunctionFactory.Create(MenuTools.GetSpecials),
            AIFunctionFactory.Create(MenuTools.GetItemPrice)
        ]);

    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("\n=== AF Agent Response ===\n");

    var result = await agent.RunAsync(userInput);
    Console.WriteLine(result);
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
