// Copyright (c) Microsoft. All rights reserved.

using Azure.Identity;
using Microsoft.Agents.AI.Hosting;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

builder.AddAzureChatCompletionsClient(connectionName: "foundry",
    configureSettings: settings =>
        {
            // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
            // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
            // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
            settings.TokenCredential = new DefaultAzureCredential();
            settings.EnableSensitiveTelemetryData = builder.Environment.IsDevelopment();
        })
    .AddChatClient("gpt41");

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
