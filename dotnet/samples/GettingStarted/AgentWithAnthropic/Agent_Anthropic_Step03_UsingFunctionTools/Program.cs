// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools.
// It shows both non-streaming and streaming agent interactions using weather-related tools.

using System.ComponentModel;
using Anthropic;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Define the agent with function tools.
AITool tool = AIFunctionFactory.Create(GetWeather);

// Get anthropic client to create agents.
AIAgent agent = new AnthropicClient { APIKey = apiKey }
    .CreateAIAgent(model: model, instructions: AssistantInstructions, name: AssistantName, tools: [tool]);

// Non-streaming agent interaction with function tools.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", thread));

// Streaming agent interaction with function tools.
thread = agent.GetNewThread();
await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync("What is the weather like in Amsterdam?", thread))
{
    Console.WriteLine(update);
}
