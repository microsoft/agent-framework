// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using System;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";

const string AgentName = "GitHubAgent";
const string AgentInstructions = "ou answer questions related to GitHub repositories only.";

// Get a client to create/retrieve server side agents with.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create an MCP tool definition that the agent can use.
var mcpTool = new MCPToolDefinition(
    serverLabel: "github",
    serverUrl: "https://api.githubcopilot.com/mcp/");
var mcpToolResource = new MCPToolResource(serverLabel: "github")
{
    RequireApproval = new MCPApproval("never"),
};
var toolResources = new ToolResources
{
    Mcp = { mcpToolResource }
};

// Create a server side persistent agent with the Azure.AI.Agents.Persistent SDK.
var agentMetadata = await persistentAgentsClient.Administration.CreateAgentAsync(
    model: model,
    name: AgentName,
    instructions: AgentInstructions,
    tools: [mcpTool],
    toolResources: toolResources);

// Retrieve an already created server side persistent agent as an AIAgent.
AIAgent agent = await persistentAgentsClient.GetAIAgentAsync(agentMetadata.Value.Id);

// You can then invoke the agent like any other AIAgent.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Summarize the last four commits to the microsoft/semantic-kernel repository?", thread));

// Cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
