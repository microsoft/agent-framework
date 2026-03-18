// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent with a multi-turn conversation, where the context is preserved in the session object.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the session object.
session = await agent.CreateSessionAsync();
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}
await foreach (var update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}
