// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a multi-turn conversation agent using the Foundry Responses API directly.

using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a FoundryAgentClient that uses the Responses API directly.
// No server-side agent is created — instructions and model are provided locally.
FoundryAgentClient agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new AzureCliCredential(),
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Invoke the agent with a multi-turn conversation, where the context is preserved in the session object.
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the session object.
session = await agent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.Write(update);
}

Console.WriteLine();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.Write(update);
}

Console.WriteLine();
