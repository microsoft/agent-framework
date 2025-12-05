// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to create OpenAIResponseClientAgent directly from an OpenAIResponseClient instance.

using OpenAI;
using OpenAI.Responses;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Create an OpenAIResponseClient directly from OpenAIClient
OpenAIResponseClient responseClient = new OpenAIClient(apiKey).GetOpenAIResponseClient(model);

// Create an agent directly from the OpenAIResponseClient using OpenAIResponseClientAgent
OpenAIResponseClientAgent agent = new(responseClient, instructions: "You are good at telling jokes.", name: "Joker");

ResponseItem userMessage = ResponseItem.CreateUserMessageItem("Tell me a joke about a pirate.");

// Invoke the agent and output the text result.
OpenAIResponse response = await agent.RunAsync([userMessage]);
Console.WriteLine(response.GetOutputText());

// Invoke the agent with streaming support.
IAsyncEnumerable<StreamingResponseUpdate> responseUpdates = agent.RunStreamingAsync([userMessage]);
await foreach (StreamingResponseUpdate responseUpdate in responseUpdates)
{
    if (responseUpdate is StreamingResponseOutputTextDeltaUpdate textUpdate)
    {
        Console.WriteLine(textUpdate.Delta);
    }
}
