// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a multi-turn conversation agent with a FoundryAgent.

using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a FoundryAgent.
FoundryAgent agent = new(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Invoke the agent with a multi-turn conversation, where the context is preserved in the session object.
ChatClientAgentSession session = await agent.CreateConversationSessionAsync();

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the session object.
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
