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

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a dictionary with your fixed properties  
var inMemorySettings = new Dictionary<string, string?>
{
    { "AzureOpenAI:Endpoint", endpoint },
    { "AzureOpenAI:DeploymentName", deploymentName },
    { "AzureOpenAI:ModelId", deploymentName },
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
    type: azure_openai_agent
    name: Joker
    description: Joker Agent
    instructions: You are good at telling jokes.
    model:
      id: ${AzureOpenAI:ModelId}
      connection:
        type: azure_openai
        provider: azure_openai
        endpoint: ${AzureOpenAI:Endpoint}
        options:
          deployment_name: ${AzureOpenAI:DeploymentName}
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureOpenAIAgentFactory();
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
