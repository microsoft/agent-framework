// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI as the backend.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using OpenAI.Responses;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_CHAT_MODEL_NAME") ?? "gpt-4o-mini";

AIAgent agent =
    new ResponsesClient(model: model, apiKey: apiKey)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

var responsesClient = new ResponsesClient(model: model, apiKey: apiKey);
AIAgent agent2 = new ChatClientAgent(responsesClient.AsIChatClient());

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
Console.WriteLine(await agent2.RunAsync("Tell me a joke about a pirate."));
