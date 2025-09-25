// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Chat Completion as the backend.

using System;
using Microsoft.Agents.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");
var modelName = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

AIAgent agent = new OpenAIClient(
    apiKey)
     .GetChatClient(modelName)
     .CreateAIAgent(JokerInstructions, JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
