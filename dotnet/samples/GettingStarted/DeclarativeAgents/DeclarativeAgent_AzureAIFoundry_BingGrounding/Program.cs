// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var connectionId = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_BING_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_FOUNDRY_BING_CONNECTION_ID is not set.");
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
      - type: bing_grounding
        options:
          tool_connections:
            - {connectionId}
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateFromYamlAsync(text, creationOptions);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("What is the latest new about the Semantic Kernel?"));

// cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
