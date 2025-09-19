// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";
var vectorStoreId = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_VECTOR_STORE_ID") ?? throw new InvalidOperationException("AZURE_FOUNDRY_VECTOR_STORE_ID is not set.");

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
    name: FileSearchAgent
    instructions: Answer questions using available files to provide grounding context.
    description: This agent answers questions using available files to provide grounding context.
    model:
      id: {model}
    tools:
      - type: file_search
        description: Grounding with available files.
        options:
          vector_store_ids:
            - {vectorStoreId}
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateFromYamlAsync(text, creationOptions);

// Invoke the agent and output the text result.
var response = await agent!.RunAsync("What are the key features of the Semantic Kernel?");
Console.WriteLine(response.Text);

// cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
