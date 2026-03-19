// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools.
// It shows both non-streaming and streaming agent interactions using menu-related tools.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
{
    Thread.Sleep(1000); // simulate api call delay
    return $"The weather in {location} is cloudy with a high of 15°C.";
}

// Create the chat client and agent, and provide the function tool to the agent.
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are a helpful assistant", tools: [AIFunctionFactory.Create(GetWeather)]);

// Non-streaming agent interaction with function tools.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));

// Streaming agent interaction with function tools.
await foreach (var update in agent.RunStreamingAsync("What is the weather like in Amsterdam?"))
{
    Console.WriteLine(update);
}
