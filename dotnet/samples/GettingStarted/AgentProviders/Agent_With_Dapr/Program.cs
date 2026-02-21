// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Dapr as the backend.

using Dapr.AI.Conversation.Extensions;
using Dapr.AI.Microsoft.Extensions;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

// Register the Dapr Conversation client with dependency injection
var app = Host.CreateDefaultBuilder()
    .ConfigureServices(services =>
    {
        // Configure the gRPC port for the Dapr sidecar
        services.AddDaprConversationClient((_, builder) => builder.UseGrpcEndpoint("http://localhost:3501"));
        // Provide the name of the Conversation component loaded in the sidecar to use
        services.AddDaprChatClient(opt => opt.ConversationComponentName = "ollama");
    }).Build();

// Get an instance of the Dapr chat client from the dependency injection container
using var scope = app.Services.CreateScope();
var daprChatClient = scope.ServiceProvider.GetRequiredService<IChatClient>();

// Use this chat client to construct an AIAgent
AIAgent agent = daprChatClient.CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent and output the text result
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
