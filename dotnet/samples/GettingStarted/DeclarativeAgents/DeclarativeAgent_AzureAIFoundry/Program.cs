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

// Create the PersistentAgentsClient with AzureCliCredential for authentication.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Set up dependency injection to provide the TokenCredential implementation
var serviceCollection = new ServiceCollection();
serviceCollection.AddTransient((sp) => persistentAgentsClient);
IServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();

// Response format to ensure the output is structured.
var responseFormat = "{\"type\":\"json_schema\",\"json_schema\":{\"name\":\"assistant_response\",\"strict\":true,\"schema\":{\"$schema\":\"http://json-schema.org/draft-07/schema#\",\"type\":\"object\",\"properties\":{\"language\":{\"type\":\"string\",\"description\":\"The language of the answer.\"},\"answer\":{\"type\":\"string\",\"description\":\"The answer text.\"}},\"required\":[\"language\",\"answer\"],\"additionalProperties\":false}}}";

// Define the agent using a YAML definition.
var text =
    $"""
    kind: GptComponentMetadata
    type: azure_foundry_agent
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
    model:
      id: {model}
      options:
        temperature: 0.9
        top_p: 0.95
        response_format: {responseFormat}
    """;

// Alternatively, you can define the response format using as YAML for better readability.
var textYaml =
    $"""
    kind: GptComponentMetadata
    type: azure_foundry_agent
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
    model:
      id: {model}
      options:
        temperature: 0.9
        top_p: 0.95
        response_format:
          type: json_schema
          json_schema:
            name: assistant_response
            strict: true
            schema:
              $schema: http://json-schema.org/draft-07/schema#
              type: object
              properties:
                language:
                  type: string
                  description: The language of the answer.
                answer:
                  type: string
                  description: The answer text.
              required:
                - language
                - answer
              additionalProperties: false
    """;

// Create the agent from the YAML definition.
var agentFactory = new AzureFoundryAgentFactory();
var creationOptions = new AgentCreationOptions()
{
    ServiceProvider = serviceProvider,
};
var agent = await agentFactory.CreateFromYamlAsync(textYaml, creationOptions);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate in English."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate in French."))
{
    Console.WriteLine(update);
}

// cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
