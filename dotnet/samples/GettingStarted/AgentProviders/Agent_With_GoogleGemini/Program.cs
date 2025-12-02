// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with Google Gemini

using Google.GenAI;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Mscc.GenerativeAI.Microsoft;

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

string apiKey = Environment.GetEnvironmentVariable("GOOGLE_GENAI_API_KEY") ?? throw new InvalidOperationException("Please set the GOOGLE_GENAI_API_KEY environment variable.");
string model = Environment.GetEnvironmentVariable("GOOGLE_GENAI_MODEL") ?? "gemini-2.5-fast";

// Using a Google GenAI IChatClient implementation
// Until the PR https://github.com/googleapis/dotnet-genai/pull/81 is not merged this option
// requires usage of also both GeminiChatClient.cs and GoogleGenAIExtensions.cs polyfills to work.

ChatClientAgent agentGenAI = new(
    new Client(vertexAI: false, apiKey: apiKey).AsIChatClient(model),
    name: JokerName,
    instructions: JokerInstructions);

AgentRunResponse response = await agentGenAI.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine($"Google GenAI client based agent response:\n{response}");

// Using a community driven Mscc.GenerativeAI.Microsoft package

ChatClientAgent agentCommunity = new(
    new GeminiChatClient(apiKey, model),
    name: JokerName,
    instructions: JokerInstructions);

response = await agentCommunity.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine($"Community client based agent response:\n{response}");
