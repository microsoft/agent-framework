// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using HelloHttpApi.ApiService;
using HelloHttpApi.ApiService.A2A;
using HelloHttpApi.ApiService.Utilities;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();

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

var taskManager = new TaskManager();
var a2aAgent = new DefaultA2AAgent(loggerFactory.CreateLogger<DefaultA2AAgent>());
a2aAgent.Attach(taskManager);

app.MapA2A(taskManager, "/a2a");
app.MapHttpA2A(taskManager, "/a2a");

app.MapDefaultEndpoints();

app.Run();
