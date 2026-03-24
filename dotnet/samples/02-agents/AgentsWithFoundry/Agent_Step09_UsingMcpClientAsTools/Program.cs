// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use MCP client tools with an agent.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

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
List<AITool> agentTools = [.. mcpTools.Cast<AITool>()];

AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: "You answer questions related to GitHub repositories only.",
    name: "AgentWithMCP",
    tools: agentTools);

string prompt = "Summarize the last four commits to the microsoft/semantic-kernel repository?";

Console.WriteLine($"Invoking agent '{agent.Name}' with prompt: {prompt} ...");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync(prompt));