// Copyright (c) Microsoft. All rights reserved.

// Using Images — Multimodal input with an AI agent
//
// This sample shows how to send image content to an AI agent
// for vision-based analysis.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

var agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: deploymentName,
        instructions: "You are a helpful agent that can analyze images",
        name: "VisionAgent");

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),
    await DataContent.LoadFromAsync("Assets/walkway.jpg"),
]);

var session = await agent.CreateSessionAsync();

await foreach (var update in agent.RunStreamingAsync(message, session))
{
    Console.WriteLine(update);
}
