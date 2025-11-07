// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an AI agent as an MCP tool.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using ModelContextProtocol.Server;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes, and you always start each joke with 'Aye aye, captain!'.";
const string JokerName = "JokerAgent";
const string JokerDescription = "An agent that tells jokes.";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var agentsClient = new AgentsClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AIAgent agent = agentsClient.CreateAIAgent(
    name: JokerName,
    model: deploymentName,
    instructions: JokerInstructions,
    creationOptions: new() { Description = JokerDescription });

// Convert the agent to an AIFunction and then to an MCP tool.
// The agent name and description will be used as the mcp tool name and description.
McpServerTool tool = McpServerTool.Create(agent.AsAIFunction());

// Register the MCP server with StdIO transport and expose the tool via the server.
HostApplicationBuilder builder = Host.CreateEmptyApplicationBuilder(settings: null);
builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithTools([tool]);

Console.WriteLine("Starting MCP Tool server. Press Ctrl+C to exit.");

await builder.Build().RunAsync();
