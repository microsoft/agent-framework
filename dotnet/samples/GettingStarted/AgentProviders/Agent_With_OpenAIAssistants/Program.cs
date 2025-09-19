// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Assistants as the backend.

// WARNING: The Assistants API is deprecated and will be shut down.
// For more information see the OpenAI documentation: https://platform.openai.com/docs/assistants/migration

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

using System;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");
var mmodel = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

// Get a client to create/retrieve server side agents with.
var assistantClient = new OpenAIClient(apiKey).GetAssistantClient();

// You can create a server side assistant with the OpenAI SDK.
var createResult = await assistantClient.CreateAssistantAsync(mmodel, new() { Name = JokerName, Instructions = JokerInstructions });

// You can retrieve an already created server side assistant as an AIAgent.
AIAgent agent1 = await assistantClient.GetAIAgentAsync(createResult.Value.Id);

// You can also create a server side assistant and return it as an AIAgent directly.
AIAgent agent2 = await assistantClient.CreateAIAgentAsync(
    model: mmodel,
    name: JokerName,
    instructions: JokerInstructions);

// You can invoke the agent like any other AIAgent.
AgentThread thread = agent1.GetNewThread();
Console.WriteLine(await agent1.RunAsync("Tell me a joke about a pirate.", thread));

// Cleanup for sample purposes.
await assistantClient.DeleteAssistantAsync(agent1.Id);
await assistantClient.DeleteAssistantAsync(agent2.Id);
