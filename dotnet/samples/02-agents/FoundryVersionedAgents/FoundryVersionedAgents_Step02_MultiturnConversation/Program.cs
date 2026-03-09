// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.


using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Create a FoundryVersionedAgent for the server side agent version.
FoundryVersionedAgent jokerAgent = await FoundryVersionedAgent.CreateAIAgentAsync(name: JokerName, instructions: JokerInstructions);

// Create a conversation session — this creates a server-side conversation that appears in the Foundry Project UI.
ChatClientAgentSession session = await jokerAgent.CreateConversationSessionAsync();

Console.WriteLine(await jokerAgent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await jokerAgent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(jokerAgent);
