// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using OpenAI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddAGUIServer();

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register an AgentIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });
//
// This sample does not authenticate AG-UI callers. Multi-user hosts must configure authentication
// and enforce endpoint authorization, for example with MapAGUIServer(...).RequireAuthorization().
// For claims-based isolation of persisted sessions, call builder.Services.AddHttpContextAccessor()
// and builder.Services.UseClaimsBasedAgentIsolation(), using a claim that uniquely identifies each caller.
// See the AG-UI samples README's "Security considerations" for configuration and client requirements.

WebApplication app = builder.Build();

Uri endpoint = AzureOpenAIEndpoint.From(
    builder.Configuration["AZURE_OPENAI_ENDPOINT"])
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Create the AI agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
ChatClient chatClient = new OpenAIClient(
    new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
    new OpenAIClientOptions { Endpoint = endpoint })
    .GetChatClient(deploymentName);

AIAgent agent = chatClient.AsAIAgent(
    name: "AGUIAssistant",
    instructions: "You are a helpful assistant.");

// Map the AG-UI agent endpoint
app.MapAGUIServer("/", agent);

await app.RunAsync();
