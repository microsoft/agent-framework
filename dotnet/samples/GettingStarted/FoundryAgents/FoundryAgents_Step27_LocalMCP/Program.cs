// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a Hosted MCP (Model Context Protocol) server tool with Azure Foundry Agents.
// The MCP server runs remotely and is invoked by the Azure Foundry service when needed.
// This sample uses the Microsoft Learn MCP endpoint to search documentation.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AgentInstructions = "You are a helpful assistant that can help with Microsoft documentation questions. Use the Microsoft Learn MCP tool to search for documentation.";
const string AgentName = "DocsAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create a Hosted MCP tool that the agent can use.
// The MCP tool is hosted at Microsoft Learn and provides documentation search capabilities.
// Setting ApprovalMode to NeverRequire allows the tool to be called without user approval.
var mcpTool = new HostedMcpServerTool(
    serverName: "microsoft_learn",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};

// Create the server side agent with the MCP tool
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    model: deploymentName,
    name: AgentName,
    instructions: AgentInstructions,
    tools: [mcpTool]);

Console.WriteLine($"Agent '{agent.Name}' created successfully.");

// Ask a question that will use the MCP tool to search documentation
string prompt = "How to create an Azure storage account using az cli?";
Console.WriteLine($"\nUser: {prompt}\n");

// Invoke the agent and output the result
AgentResponse response = await agent.RunAsync(prompt);
Console.WriteLine($"Agent: {response}");

// Cleanup by removing the agent when done
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine($"\nAgent '{agent.Name}' deleted.");
