// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use image multi-modality with an agent using the Responses API directly.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

// Create a FoundryAgentClient using environment variable auto-discovery.
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use (use a vision-capable model like gpt-4o).
FoundryAgentClient agent = new(
    instructions: "You are a helpful agent that can analyze images.",
    name: "VisionAgent");

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
