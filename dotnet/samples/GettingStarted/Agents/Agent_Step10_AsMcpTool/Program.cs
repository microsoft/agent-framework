// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an AI agent as an MCP tool.

using System;
using Agent_Step10_AsMcpTool;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes, and you always start each joke with 'Aye aye, captain!'.";

var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create a server side persistent agent
var agentMetadata = await persistentAgentsClient.Administration.CreateAgentAsync(
    model: deploymentName,
    name: JokerName,
    instructions: JokerInstructions);

// Retrieve the server side persistent agent as an AIAgent.
AIAgent agent = await persistentAgentsClient.GetAIAgentAsync(agentMetadata.Value.Id);

// Register the MCP server with StdIO transport and expose the agent as an MCP tool.
HostApplicationBuilder builder = Host.CreateEmptyApplicationBuilder(settings: null);
builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithTools([agent.AsMcpTool()]);

await builder.Build().RunAsync();
