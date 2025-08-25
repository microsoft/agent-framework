// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
     .GetChatClient(azureOpenAIDeploymentName)
     .CreateAIAgent(JokerInstructions, JokerName);

// Invoke the agent with a multi-turn conversation, where the context is preserved in the thread object.
Console.WriteLine("\n--- Run with a thread (context preserved) ---\n");
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the thread object.
Console.WriteLine("\n--- Run with a thread and streaming (context preserved) ---\n");
thread = agent.GetNewThread();
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate.", thread))
{
    Console.WriteLine(update);
}
await foreach (var update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread))
{
    Console.WriteLine(update);
}
