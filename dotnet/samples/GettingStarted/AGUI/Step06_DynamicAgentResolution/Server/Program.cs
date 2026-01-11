// Copyright (c) Microsoft. All rights reserved.

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

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Create chat client (shared across agents)
ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

// Define available agent configurations
Dictionary<string, (string Name, string Instructions)> agentConfigs = new(StringComparer.OrdinalIgnoreCase)
{
    ["general"] = ("GeneralAssistant", "You are a helpful general assistant."),
    ["code"] = ("CodeAssistant", "You are an expert programmer. Help users write, debug, and optimize code."),
    ["writer"] = ("WriterAssistant", "You are a professional writer. Help users with writing, editing, and creative content.")
};

// Map AG-UI endpoint with dynamic agent resolution
app.MapAGUI("/agents/{agentId}", async (HttpContext context, CancellationToken cancellationToken) =>
{
    // Extract agent ID from route
    string? agentId = context.GetRouteValue("agentId")?.ToString();

    if (string.IsNullOrEmpty(agentId))
    {
        return null;
    }

    // Look up agent configuration
    if (!agentConfigs.TryGetValue(agentId, out (string Name, string Instructions) config))
    {
        return null; // Returns 404
    }

    // Create and return agent (could also cache this)
    IChatClient client = chatClient.AsIChatClient();
    return client.CreateAIAgent(
        name: config.Name,
        instructions: config.Instructions);
});

// Also map a root endpoint for discovery
app.MapGet("/", () => Results.Json(new
{
    availableAgents = agentConfigs.Keys.ToArray(),
    usage = "POST to /agents/{agentId} with AG-UI protocol"
}));

await app.RunAsync();
