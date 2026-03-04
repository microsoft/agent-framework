// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a multi-turn conversation agent using the Foundry Responses API directly.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

// Create a FoundryAgentClient that uses the Responses API directly.
// No server-side agent is created — instructions and model are provided locally.
// The endpoint and model are resolved from environment variables:
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
// Authentication uses DefaultAzureCredential.
FoundryAgentClient agent = new(
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
