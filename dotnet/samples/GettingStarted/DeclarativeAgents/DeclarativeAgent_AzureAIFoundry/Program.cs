// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using System.Collections.Generic;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";

// Create a dictionary with your fixed properties  
var inMemorySettings = new Dictionary<string, string?>
{
    { "AzureFoundry:Endpoint", endpoint },
    { "AzureFoundry:ModelId", model },
};

// Build the IConfiguration instance to allow for variable substitution in the YAML definition
IConfiguration configuration = new ConfigurationBuilder()
    .AddInMemoryCollection(inMemorySettings)
    .Build();

// Set up dependency injection to provide the TokenCredential implementation
var serviceCollection = new ServiceCollection();
serviceCollection.AddTransient<TokenCredential, AzureCliCredential>();
IServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();

// Define the agent using a YAML definition.
var text =
    """
    type: azure_foundry_agent
    name: Joker
    description: Joker Agent
    instructions: You are good at telling jokes.
    model:
      id: ${AzureFoundry:ModelId}
      connection:
        type: azure_foundry
        provider: azure_foundry
        endpoint: ${AzureFoundry:Endpoint}
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    Configuration = configuration,
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateAgentFromYamlAsync(text, creationOptions);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
