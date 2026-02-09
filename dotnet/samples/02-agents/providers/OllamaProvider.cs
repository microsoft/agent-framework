// Copyright (c) Microsoft. All rights reserved.

// Provider: Ollama
// Create an agent using Ollama as the backend for local model inference.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OllamaSharp;

var endpoint = Environment.GetEnvironmentVariable("OLLAMA_ENDPOINT")
    ?? throw new InvalidOperationException("OLLAMA_ENDPOINT is not set.");
var modelName = Environment.GetEnvironmentVariable("OLLAMA_MODEL_NAME")
    ?? throw new InvalidOperationException("OLLAMA_MODEL_NAME is not set.");

// <ollama>
AIAgent agent = new OllamaApiClient(new Uri(endpoint), modelName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");
// </ollama>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
