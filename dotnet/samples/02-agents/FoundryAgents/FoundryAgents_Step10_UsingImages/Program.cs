// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use image multi-modality with an agent.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

FoundryAgent agent = new(instructions: "You are a helpful agent that can analyze images.", name: "VisionAgent");

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),
    await DataContent.LoadFromAsync("assets/walkway.jpg"),
]);

AgentSession session = await agent.CreateSessionAsync();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(message, session))
{
    Console.Write(update);
}

Console.WriteLine();
