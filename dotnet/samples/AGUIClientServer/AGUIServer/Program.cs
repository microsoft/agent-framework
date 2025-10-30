// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using OpenAI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Map the AG-UI agent endpoint
app.MapAGUIAgent("/", (messages) =>
{
    return new AzureOpenAIClient(
            new Uri(endpoint),
            new DefaultAzureCredential())
        .GetChatClient(deploymentName)
        .CreateAIAgent(name: "AGUIAssistant");
});

await app.RunAsync();
