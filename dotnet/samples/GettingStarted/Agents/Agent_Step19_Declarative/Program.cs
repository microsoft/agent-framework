// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create an agent from a YAML based declarative representation.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the chat client
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .AsIChatClient();

// Define the agent using a YAML definition.
var text =
    """
    kind: Prompt
    name: Assistant
    description: Helpful assistant
    instructions: You are a helpful assistant. You answer questions in the language specified by the user. You return your answers in a JSON format.
    model:
        options:
            temperature: 0.9
            topP: 0.95
    outputSchema:
        properties:
            language:
                type: string
                required: true
                description: The language of the answer.
            answer:
                type: string
                required: true
                description: The answer text.
    """;

// Create the agent from the YAML definition.
var agentFactory = new ChatClientPromptAgentFactory(chatClient);
var agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate in English."));

// Invoke the agent with streaming support.
await foreach (var update in agent!.RunStreamingAsync("Tell me a joke about a pirate in French."))
{
    Console.WriteLine(update);
}
