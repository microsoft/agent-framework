// Copyright (c) Microsoft. All rights reserved.

// Local MCP Tools
// Use tools from a local MCP (Model Context Protocol) server via stdio transport.
// The agent discovers and invokes MCP tools from an external process.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <local_mcp>
// Start a local MCP server process (e.g., the GitHub MCP server)
await using var mcpClient = await McpClient.CreateAsync(new StdioClientTransport(new()
{
    Name = "MCPServer",
    Command = "npx",
    Arguments = ["-y", "--verbose", "@modelcontextprotocol/server-github"],
}));

// Discover available tools from the MCP server
IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "AgentWithMCP",
    model: deploymentName,
    instructions: "You answer questions related to GitHub repositories only.",
    tools: [.. mcpTools.Cast<AITool>()]);

Console.WriteLine(await agent.RunAsync("Summarize the last four commits to the microsoft/semantic-kernel repository?"));
// </local_mcp>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
