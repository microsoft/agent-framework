// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var agentId = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_AGENT_ID") ?? throw new InvalidOperationException("AZURE_FOUNDRY_AGENT_ID is not set.");

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
    id: {agentId}
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateFromYamlAsync(text, creationOptions);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

// cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
