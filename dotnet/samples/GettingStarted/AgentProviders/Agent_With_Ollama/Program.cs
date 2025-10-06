// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Ollama as the backend.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OllamaSharp;

var endpoint = Environment.GetEnvironmentVariable("OLLAMA_ENDPOINT") ?? throw new InvalidOperationException("OLLAMA_ENDPOINT is not set.");
var modelName = Environment.GetEnvironmentVariable("OLLAMA_MODEL_NAME") ?? throw new InvalidOperationException("OLLAMA_MODEL_NAME is not set.");

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

// Get a chat client for Ollama and use it to construct an AIAgent.
AIAgent agent = new OllamaApiClient(new Uri(endpoint), modelName)
    .CreateAIAgent(JokerInstructions, JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
