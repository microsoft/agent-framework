// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an AI agent as an MCP tool.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using ModelContextProtocol.Server;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var aiProjectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());

// Create a server side agent and expose it as an AIAgent.
ProjectsAgentVersion agentVersion = await aiProjectClient.AgentAdministrationClient.CreateAgentVersionAsync(
    "Joker",
    new ProjectsAgentVersionCreationOptions(
        new DeclarativeAgentDefinition(model: deploymentName)
        {
            Instructions = "You are good at telling jokes, and you always start each joke with 'Aye aye, captain!'.",
        })
    {
        Description = "An agent that tells jokes.",
    });
AIAgent agent = aiProjectClient.AsAIAgent(agentVersion);

// Convert the agent to an AIFunction and then to an MCP tool.
// The agent name and description will be used as the mcp tool name and description.
McpServerTool tool = McpServerTool.Create(agent.AsAIFunction());

// Register the MCP server with StdIO transport and expose the tool via the server.
HostApplicationBuilder builder = Host.CreateEmptyApplicationBuilder(settings: null);
builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithTools([tool]);

await builder.Build().RunAsync();
