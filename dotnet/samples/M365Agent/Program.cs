// Copyright (c) Microsoft. All rights reserved.

// Sample that shows how to create an Agent Framework agent that is hosted using the M365 Agent SDK.
// The agent can then be consumed from various M365 channels.
// See the README.md for more information.

using Azure.AI.OpenAI;
using Azure.Identity;
using M365Agent;
using M365Agent.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OpenAI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

if (builder.Environment.IsDevelopment())
{
    builder.Configuration.AddUserSecrets<Program>();
}

builder.Services.AddHttpClient();

// Register the inference service of your choice. AzureOpenAI and OpenAI are demonstrated...
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

// Add the WeatherForecastAgent plus a welcome message.
// These will be consumed by the AFAgentApplication and exposed as an Agent SDK AgentApplication.
builder.Services.AddSingleton<AIAgent, WeatherForecastAgent>();
builder.Services.AddKeyedSingleton("AFAgentApplicationWelcomeMessage", "Hello and Welcome! I'm here to help with all your weather forecast needs!");

// Add the AgentApplication, which contains the logic for responding to
// user messages via the Agent SDK.
builder.AddAgent<AFAgentApplication>();

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

// This receives incoming messages and routes them to the registered AgentApplication.
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
