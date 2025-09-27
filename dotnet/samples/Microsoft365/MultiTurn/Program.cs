﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using MultiTurn;
using OpenAI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

if (builder.Environment.IsDevelopment())
{
    builder.Configuration.AddUserSecrets<Program>();
}

builder.Services.AddHttpClient();

// Register the AIAgent of your choice. AzureOpenAI and OpenAI are demonstrated...
IChatClient chatClient;
if (builder.Configuration.GetSection("AIServices").GetValue<bool>("UseAzureOpenAI"))
{
    var deploymentName = builder.Configuration.GetSection("AIServices:AzureOpenAI").GetValue<string>("DeploymentName")!;
    var endpoint = builder.Configuration.GetSection("AIServices:AzureOpenAI").GetValue<string>("Endpoint")!;

    chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new AzureCliCredential())
         .GetChatClient(deploymentName)
         .AsIChatClient();
}
else
{
    var modelId = builder.Configuration.GetSection("AIServices:OpenAI").GetValue<string>("ModelId")!;
    var apiKey = builder.Configuration.GetSection("AIServices:OpenAI").GetValue<string>("ApiKey")!;

    chatClient = new OpenAIClient(
        apiKey)
        .GetChatClient(modelId)
        .AsIChatClient();
}
builder.Services.AddSingleton(chatClient);

// Add AgentApplicationOptions from appsettings section "AgentApplication".
builder.AddAgentApplicationOptions();

// Add the AgentApplication, which contains the logic for responding to
// user messages.
builder.AddAgent<MyAgent>();

// Register IStorage.  For development, MemoryStorage is suitable.
// For production Agents, persisted storage should be used so
// that state survives Agent restarts, and operates correctly
// in a cluster of Agent instances.
builder.Services.AddSingleton<IStorage, MemoryStorage>();

// Configure the HTTP request pipeline.

// Add AspNet token validation for Azure Bot Service and Entra.  Authentication is
// configured in the appsettings.json "TokenValidation" section.
builder.Services.AddControllers();
builder.Services.AddAgentAspNetAuthentication(builder.Configuration);

WebApplication app = builder.Build();

// Enable AspNet authentication and authorization
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/", () => "Microsoft Agents SDK Sample");

// This receives incoming messages from Azure Bot Service or other SDK Agents
var incomingRoute = app.MapPost("/api/messages", async (HttpRequest request, HttpResponse response, IAgentHttpAdapter adapter, IAgent agent, CancellationToken cancellationToken) => await adapter.ProcessAsync(request, response, agent, cancellationToken));

if (!app.Environment.IsDevelopment())
{
    incomingRoute.RequireAuthorization();
}
else
{
    // Hardcoded for brevity and ease of testing. 
    // In production, this should be set in configuration.
    app.Urls.Add("http://localhost:3978");
}

app.Run();
