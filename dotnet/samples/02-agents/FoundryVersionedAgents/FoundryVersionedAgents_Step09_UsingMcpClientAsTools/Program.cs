// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an AI agent as an MCP tool.

using Azure.AI.Projects;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

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

Console.WriteLine($"Creating the agent '{agentName}' ...");

// Define the agent you want to create. (Prompt Agent in this case)
FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
    name: agentName,
    instructions: "You answer questions related to GitHub repositories only.",
    tools: [.. mcpTools.Cast<AITool>()]);

string prompt = "Summarize the last four commits to the microsoft/semantic-kernel repository?";

Console.WriteLine($"Invoking agent '{agent.Name}' with prompt: {prompt} ...");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync(prompt));

// Clean up the agent after use.
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
