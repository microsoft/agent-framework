// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using System.ComponentModel;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";

// Create the PersistentAgentsClient with AzureCliCredential for authentication.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Set up dependency injection to provide the TokenCredential implementation
var serviceCollection = new ServiceCollection();
serviceCollection.AddTransient((sp) => persistentAgentsClient);
IServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();

// Define the agent using a YAML definition.
var text =
    $"""
    kind: GptComponentMetadata
    type: azure_foundry_agent
    name: CoderAgent
    description: Coder Agent
    instructions: You write code to solve problems.
    model:
      id: {model}
    tools:
      - id: GetSpecials
        type: function
        description: Get the specials from the menu.
      - id: GetItemPrice
        type: function
        description: Get the price of an item on the menu.
        options:
          parameters:
            - name: menuItem
              type: string
              required: true
              description: The name of the menu item.
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateFromYamlAsync(text, creationOptions);

// Create run options with the function tool.
var menuPlugin = new Sample.MenuPlugin();
var chatOptions = new ChatOptions()
{
    Tools = [
        AIFunctionFactory.Create(menuPlugin.GetSpecials),
        AIFunctionFactory.Create(menuPlugin.GetItemPrice),
    ]
};
var runOptions = new ChatClientAgentRunOptions(chatOptions);

// Invoke the agent and output the text result.
var response = await agent!.RunAsync("What is the special soup and how much does it cost?", options: runOptions);
Console.WriteLine(response.Text);

// cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

namespace Sample
{
    public sealed class MenuPlugin
    {
        [Description("Provides a list of specials from the menu.")]
        public MenuItem[] GetMenu()
        {
            return s_menuItems;
        }

        [Description("Provides a list of specials from the menu.")]
        public MenuItem[] GetSpecials()
        {
            return [.. s_menuItems.Where(i => i.IsSpecial)];
        }

        [Description("Provides the price of the requested menu item.")]
        public float? GetItemPrice(
            [Description("The name of the menu item.")]
            string menuItem)
        {
            return s_menuItems.FirstOrDefault(i => i.Name.Equals(menuItem, StringComparison.OrdinalIgnoreCase))?.Price;
        }

        private static readonly MenuItem[] s_menuItems =
            [
                new()
            {
                Category = "Soup",
                Name = "Clam Chowder",
                Price = 4.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Soup",
                Name = "Tomato Soup",
                Price = 4.95f,
                IsSpecial = false,
            },
            new()
            {
                Category = "Salad",
                Name = "Cobb Salad",
                Price = 9.99f,
            },
            new()
            {
                Category = "Salad",
                Name = "House Salad",
                Price = 4.95f,
            },
            new()
            {
                Category = "Drink",
                Name = "Chai Tea",
                Price = 2.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Drink",
                Name = "Soda",
                Price = 1.95f,
            },
        ];

        public sealed class MenuItem
        {
            public string Category { get; init; } = string.Empty;
            public string Name { get; init; } = string.Empty;
            public float Price { get; init; }
            public bool IsSpecial { get; init; }
        }
    }
}
