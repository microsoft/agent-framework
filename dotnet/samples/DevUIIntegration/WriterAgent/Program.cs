// Copyright (c) Microsoft. All rights reserved.

using Azure.Identity;
using Microsoft.Agents.AI.Hosting;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

builder.AddAzureChatCompletionsClient(connectionName: "foundry",
    configureSettings: settings =>
        {
            settings.TokenCredential = new DefaultAzureCredential();
            settings.EnableSensitiveTelemetryData = true;
        })
    .AddChatClient("gpt-4.1");

builder.AddAIAgent("writer", "You write short stories (300 words or less) about the specified topic.");

// Register services for OpenAI responses and conversations
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

var app = builder.Build();

// Map OpenAI API endpoints — DevUI aggregator routes requests here
app.MapOpenAIResponses();
app.MapOpenAIConversations();

app.MapDefaultEndpoints();

app.Run();
