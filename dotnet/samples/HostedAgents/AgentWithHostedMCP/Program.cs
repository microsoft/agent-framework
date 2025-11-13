// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Responses as the backend, that uses a Hosted MCP Tool.
// In this case the OpenAI responses service will invoke any MCP tools as required. MCP tools are not invoked by the Agent Framework.
// The sample demonstrates how to use MCP tools with auto approval by setting ApprovalMode to NeverRequire.

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create an MCP tool that can be called without approval.
AITool mcpTool = new HostedMcpServerTool(serverName: "microsoft_learn", serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};

// Create an agent with the MCP tool using Azure OpenAI Responses.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgent",
        tools: [mcpTool]);

await agent.RunAIAgentAsync();
