// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a basic AG-UI server hosting a chat agent for the Blazor web client.

using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using OpenAI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register an AgentIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

WebApplication app = builder.Build();

Uri endpoint = AzureOpenAIEndpoint.From(
    builder.Configuration["AZURE_OPENAI_ENDPOINT"])
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Create the AI agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
OpenAIClient azureOpenAIClient = new(
    new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
    new OpenAIClientOptions { Endpoint = endpoint });

ChatClient chatClient = azureOpenAIClient.GetChatClient(deploymentName);

ChatClientAgent agent = chatClient.AsAIAgent(
    name: "ChatAssistant",
    instructions: "You are a helpful assistant.");

// Map the AG-UI agent endpoint
app.MapAGUIServer("/ag-ui", agent);

await app.RunAsync();
