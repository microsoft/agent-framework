// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create AI agent declaratively with Azure OpenAI as the backend.

using System;
using Microsoft.Agents.Declarative;

// Define the agent using a YAML definition.
var text =
    """
    kind: GptComponentMetadata
    displayName: =Env.Foo
    type: chat_client_agent
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions is the language specified by the user.
    model:
      id: =Env.OPENAI_MODEL
      options:
        temperature: 0.9
        top_p: 0.95
    connection:
      type: openai
      options:
        api_key: =Env.OPENAI_APIKEY
    """;

// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate in English."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate in French."))
{
    Console.WriteLine(update);
}
