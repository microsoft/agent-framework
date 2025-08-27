// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools.
// It shows both non-streaming and streaming agent interactions using menu-related tools.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using SampleApp;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Define the menu tools to be used by the agent.
var menuTools = new MenuTools();

// Define the options for the chat client agent, including function tools.
var agentOptions = new ChatClientAgentOptions(
    name: "Host",
    instructions: "Answer questions about the menu",
    tools: [
        AIFunctionFactory.Create(menuTools.GetMenu),
        AIFunctionFactory.Create(menuTools.GetSpecials),
        AIFunctionFactory.Create(menuTools.GetItemPrice)
    ]);

// Create the chat client and agent.
AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
     .GetChatClient(azureOpenAIDeploymentName)
     .CreateAIAgent(agentOptions);

// Non-streaming agent interaction with function tools.
Console.WriteLine("\n--- Run with function tools ---\n");
AgentThread thread = agent.GetNewThread();
await RunAgentAsync("Hello");
await RunAgentAsync("What is the special soup and its price?");
await RunAgentAsync("What is the special drink and its price?");
await RunAgentAsync("Thank you");

async Task RunAgentAsync(string input)
{
    Console.WriteLine($"\nUser: {input}");
    var response = await agent.RunAsync(input, thread);
    Console.WriteLine($"Agent: {response}");
}

// Streaming agent interaction with function tools.
Console.WriteLine("\n--- Run with function tools and streaming ---\n");
thread = agent.GetNewThread();
await RunAgentStreamingAsync("Hello");
await RunAgentStreamingAsync("What is the special soup and its price?");
await RunAgentStreamingAsync("What is the special drink and its price?");
await RunAgentStreamingAsync("Thank you");

async Task RunAgentStreamingAsync(string input)
{
    Console.WriteLine($"\nUser: {input}");
    await foreach (var update in agent.RunStreamingAsync(input, thread))
    {
        Console.Write(update);
    }
    Console.WriteLine();
}

namespace SampleApp
{
    /// <summary>
    /// MenuTools class as used in the agent's function tools.
    /// </summary>
    internal sealed class MenuTools
    {
        private static readonly MenuItem[] s_menuItems = [
            new() { Category = "Soup", Name = "Clam Chowder", Price = 4.95f, IsSpecial = true },
            new() { Category = "Soup", Name = "Tomato Soup", Price = 4.95f, IsSpecial = false },
            new() { Category = "Salad", Name = "Cobb Salad", Price = 9.99f },
            new() { Category = "Salad", Name = "House Salad", Price = 4.95f },
            new() { Category = "Drink", Name = "Chai Tea", Price = 2.95f, IsSpecial = true },
            new() { Category = "Drink", Name = "Soda", Price = 1.95f },
        ];

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

        public sealed class MenuItem
        {
            public string Category { get; set; } = string.Empty;
            public string Name { get; set; } = string.Empty;
            public float Price { get; set; }
            public bool IsSpecial { get; set; }
        }
    }
}
