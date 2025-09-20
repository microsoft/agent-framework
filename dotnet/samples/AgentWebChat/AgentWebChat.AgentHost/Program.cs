// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AgentWebChat.AgentHost;
using AgentWebChat.AgentHost.Utilities;
using Microsoft.Agents.Orchestration;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Hosting.A2A.AspNetCore;
using Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();
builder.Services.AddOpenApi();

// Add services to the container.
builder.Services.AddProblemDetails();

// Add CosmosDB client integration
builder.AddAzureCosmosClient("agent-web-chat-cosmosdb", null, CosmosClientOptions =>
{
    CosmosClientOptions.ApplicationName = "AgentWebChat";
    CosmosClientOptions.ConnectionMode = ConnectionMode.Direct;
    CosmosClientOptions.ConsistencyLevel = ConsistencyLevel.Session;
    CosmosClientOptions.UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        TypeInfoResolver = CosmosActorStateJsonContext.Default
    };
});

// Configure the chat model and our agent.
builder.AddKeyedChatClient("chat-model");

builder.AddAIAgent(
    "pirate",
    instructions: "You are a pirate. Speak like a pirate",
    description: "An agent that speaks like a pirate.",
    chatClientServiceKey: "chat-model");

builder.AddAIAgent("knights-and-knaves", (sp, key) =>
{
    var chatClient = sp.GetRequiredKeyedService<IChatClient>("chat-model");

    ChatClientAgent knight = new(
        chatClient,
        """
        You are a knight. This means that you must always tell the truth. Your name is Alice.
        Bob is standing next to you. Bob is a knave, which means he always lies.
        When replying, always start with your name (Alice). Eg, "Alice: I am a knight."
        """, "Alice");

    ChatClientAgent knave = new(
        chatClient,
        """
        You are a knave. This means that you must always lie. Your name is Bob.
        Alice is standing next to you. Alice is a knight, which means she always tells the truth.
        When replying, always include your name (Bob). Eg, "Bob: I am a knight."
        """, "Bob");

    ChatClientAgent narrator = new(
        chatClient,
        """
        You are are the narrator of a puzzle involving knights (who always tell the truth) and knaves (who always lie).
        The user is going to ask questions and guess whether Alice or Bob is the knight or knave.
        Alice is standing to one side of you. Alice is a knight, which means she always tells the truth.
        Bob is standing to the other side of you. Bob is a knave, which means he always lies.
        When replying, always include your name (Narrator).
        Once the user has deduced what type (knight or knave) both Alice and Bob are, tell them whether they are right or wrong.
        If the user asks a general question about their surrounding, make something up which is consistent with the scenario.
        """, "Narrator");

    return new ConcurrentOrchestration([knight, knave, narrator], name: key);
});

// Add CosmosDB state storage to override default storage
builder.Services.AddCosmosActorStateStorage("actor-state-db", "ActorState");

var app = builder.Build();

app.MapOpenApi();
app.UseSwaggerUI(options => options.SwaggerEndpoint("/openapi/v1.json", "Agents API"));

// Configure the HTTP request pipeline.
app.UseExceptionHandler();

app.MapActors();

// attach a2a with simple message communication
app.AttachA2A(agentName: "pirate", path: "/a2a/pirate");
app.AttachA2A(agentName: "knights-and-knaves", path: "/a2a/knights-and-knaves", agentCard: new()
{
    Name = "Knights and Knaves",
    Description = "An agent that helps you solve the knights and knaves puzzle.",
    Version = "1.0",

    // Url can be not set, and SDK will help assign it.
    // Url = "http://localhost:5390/a2a/knights-and-knaves"
});

// Map the agents HTTP endpoints
app.MapAgentDiscovery("/agents");

app.MapDefaultEndpoints();
app.Run();
