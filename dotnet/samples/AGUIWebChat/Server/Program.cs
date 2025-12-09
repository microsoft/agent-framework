// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a basic AG-UI server hosting a chat agent for the Blazor web client.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUI();

WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Create the AI agent
AzureOpenAIClient azureOpenAIClient = new(
    new Uri(endpoint),
    new DefaultAzureCredential());

ChatClient chatClient = azureOpenAIClient.GetChatClient(deploymentName);

ChatClientAgent agent = chatClient.AsIChatClient().CreateAIAgent(
    name: "ChatAssistant",
    instructions: "You are a helpful assistant.");

// Map the AG-UI agent endpoint
app.MapAGUI("/ag-ui", agent);

await app.RunAsync();
