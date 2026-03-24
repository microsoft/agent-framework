// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use image multi-modality with an agent.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

FoundryAgent agent = aiProjectClient.AsAIAgent(deploymentName,
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
