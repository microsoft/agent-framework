// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI as the backend.

using System.ClientModel;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

UserChatMessage chatMessage = new("Tell me a joke about a pirate.");

// Invoke the agent and output the text result.
ChatCompletion chatCompletion = await agent.RunAsync([chatMessage]);
Console.WriteLine(chatCompletion.Content.Last().Text);

// Invoke the agent with streaming support.
AsyncCollectionResult<StreamingChatCompletionUpdate> completionUpdates = agent.RunStreamingAsync([chatMessage]);
await foreach (StreamingChatCompletionUpdate completionUpdate in completionUpdates)
{
    if (completionUpdate.ContentUpdate.Count > 0)
    {
        Console.WriteLine(completionUpdate.ContentUpdate[0].Text);
    }
}
