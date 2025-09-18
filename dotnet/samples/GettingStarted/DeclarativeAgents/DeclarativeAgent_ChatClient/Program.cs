// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create AI agent declaratively with Azure OpenAI as the backend.

using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the chat client
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .AsIChatClient();

// Response format to ensure the output is structured.
var responseFormat = "{\"type\":\"json_schema\",\"json_schema\":{\"name\":\"assistant_response\",\"strict\":true,\"schema\":{\"$schema\":\"http://json-schema.org/draft-07/schema#\",\"type\":\"object\",\"properties\":{\"language\":{\"type\":\"string\",\"description\":\"The language of the answer.\"},\"answer\":{\"type\":\"string\",\"description\":\"The answer text.\"}},\"required\":[\"language\",\"answer\"],\"additionalProperties\":false}}}";

// Define the agent using a YAML definition.
var text =
    $"""
    kind: GptComponentMetadata
    type: chat_client_agent
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
    model:
      options:
        temperature: 0.9
        top_p: 0.95
        response_format: {responseFormat}
    """;

// Alternatively, you can define the response format using as YAML for better readability.
/*
var textYaml =
    """
    kind: GptComponentMetadata
    type: chat_client_agent
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
    model:
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
*/

// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(text, new() { ChatClient = chatClient });

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate in English."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate in French."))
{
    Console.WriteLine(update);
}
