// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an AI agent as an MCP tool.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.WriteLine("Starting MCP Stdio for @modelcontextprotocol/server-github ... ");

// Create an MCPClient for the GitHub server
await using var mcpClient = await McpClient.CreateAsync(new StdioClientTransport(new()
{
    Name = "MCPServer",
    Command = "npx",
    Arguments = ["-y", "--verbose", "@modelcontextprotocol/server-github"],
}));

// Retrieve the list of tools available on the GitHub server
IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();
string agentName = "AgentWithMCP";
// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

Console.WriteLine($"Creating the agent '{agentName}' ...");

// Define the agent you want to create. (Prompt Agent in this case)
AIAgent agent = aiProjectClient.CreateAIAgent(
    name: agentName,
    model: deploymentName,
    instructions: "You answer questions related to GitHub repositories only.",
    tools: [.. mcpTools.Cast<AITool>()]);

string prompt = "Summarize the last four commits to the microsoft/semantic-kernel repository?";

Console.WriteLine($"Invoking agent '{agent.Name}' with prompt: {prompt} ...");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync(prompt));

// Clean up the agent after use.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
