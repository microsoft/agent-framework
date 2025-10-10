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

// Note: To use structured output with Ollama, you must use ChatClientAgent and set useJsonSchemaResponseFormat: false
// because Ollama models do not support native JSON schema validation.
// Example:
//
// using System.Text.Json.Serialization;
// using Microsoft.Extensions.AI;
//
// class JokeInfo
// {
//     [JsonPropertyName("setup")]
//     public string? Setup { get; set; }
//
//     [JsonPropertyName("punchline")]
//     public string? Punchline { get; set; }
// }
//
// // Cast OllamaApiClient to IChatClient and create a ChatClientAgent
// IChatClient chatClient = new OllamaApiClient(new Uri(endpoint), modelName);
// ChatClientAgent structuredAgent = chatClient.CreateAIAgent(
//     instructions: "You are good at telling jokes. Always respond with valid JSON containing 'setup' and 'punchline' fields.",
//     name: JokerName);
//
// var structuredResponse = await structuredAgent.RunAsync<JokeInfo>(
//     "Tell me a joke about a pirate.",
//     useJsonSchemaResponseFormat: false);
//
// Console.WriteLine($"Setup: {structuredResponse.Result?.Setup}");
// Console.WriteLine($"Punchline: {structuredResponse.Result?.Punchline}");
