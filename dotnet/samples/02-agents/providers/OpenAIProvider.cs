// Copyright (c) Microsoft. All rights reserved.

// Provider: OpenAI
// Create an agent using OpenAI Chat Completion as the backend.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// <openai>
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");
// </openai>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
