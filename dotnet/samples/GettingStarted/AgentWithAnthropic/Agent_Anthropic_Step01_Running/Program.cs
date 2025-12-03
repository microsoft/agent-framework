// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Anthropic as the backend.

using Anthropic;
using Anthropic.Core;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";

AIAgent agent = new AnthropicClient(new ClientOptions { APIKey = apiKey })
    .CreateAIAgent(model: model, instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent and output the text result.
var response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);

// Invoke the agent with streaming support.
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
