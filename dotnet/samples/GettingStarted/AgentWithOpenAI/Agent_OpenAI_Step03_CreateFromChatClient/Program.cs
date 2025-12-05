// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to create an AI agent directly from an OpenAI.Chat.ChatClient instance using OpenAIChatClientAgent.

using OpenAI;
using OpenAI.Chat;

string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Create a ChatClient directly from OpenAIClient
ChatClient chatClient = new OpenAIClient(apiKey).GetChatClient(model);

// Create an agent directly from the ChatClient using OpenAIChatClientAgent
OpenAIChatClientAgent agent = new(chatClient, instructions: "You are good at telling jokes.", name: "Joker");

UserChatMessage chatMessage = new("Tell me a joke about a pirate.");

// Invoke the agent and output the text result.
ChatCompletion chatCompletion = await agent.RunAsync([chatMessage]);
Console.WriteLine(chatCompletion.Content.Last().Text);

// Invoke the agent with streaming support.
IAsyncEnumerable<StreamingChatCompletionUpdate> completionUpdates = agent.RunStreamingAsync([chatMessage]);
await foreach (StreamingChatCompletionUpdate completionUpdate in completionUpdates)
{
    if (completionUpdate.ContentUpdate.Count > 0)
    {
        Console.WriteLine(completionUpdate.ContentUpdate[0].Text);
    }
}
