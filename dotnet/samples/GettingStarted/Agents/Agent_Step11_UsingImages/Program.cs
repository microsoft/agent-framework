// Copyright (c) Microsoft. All rights reserved.

// This sample shows how use Image Multi-Modality with an AI agent.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create a server side persistent agent
AIAgent agent = await persistentAgentsClient.CreateAIAgentAsync(
    model: deploymentName,
    name: "VisionAgent",
    instructions: "You are a helpful agent that can analyze images");

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),

    // A single yellow pixel Base64 encoded PNG image
    new DataContent("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==", "image/png")
]);

var thread = agent.GetNewThread();
var response = await agent.RunAsync(message, thread);

Console.WriteLine(response);

await persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId);
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
