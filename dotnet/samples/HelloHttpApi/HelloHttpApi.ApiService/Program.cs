// Copyright (c) Microsoft. All rights reserved.

using HelloHttpApi.ApiService;
using HelloHttpApi.ApiService.A2A;
using HelloHttpApi.ApiService.Utilities;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();

// Add CosmosDB client integration
builder.AddAzureCosmosClient("hello-http-api-cosmosdb");

// Add services to the container.
builder.Services.AddProblemDetails();

// Configure the chat model and our agent.
builder.AddKeyedChatClient("chat-model");

builder.AddAIAgent(
    name: "pirate",
    instructions: "You are a pirate. Speak like a pirate.",
    chatClientKey: "chat-model");

var app = builder.Build();
var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();

// Configure the HTTP request pipeline.
app.UseExceptionHandler();

// Map the agents HTTP endpoints
app.MapAgents();

// Configure agent to A2A communication
app.AttachA2A(
    agentName: "pirate",
    path: "/a2a");

app.MapDefaultEndpoints();

app.Run();
