// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Responses as the backend, that uses a Hosted MCP Tool.
// In this case the OpenAI responses service will invoke any MCP tools as required. MCP tools are not invoked by the Agent Framework.
// The sample demonstrates how to use MCP tools with human-in-the-loop approval by setting ApprovalMode to AlwaysRequire.
// When a tool call is requested, the caller must explicitly approve or deny it before the agent proceeds.

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create an MCP tool that requires human approval before each invocation.
// Unlike the AgentWithHostedMCP sample (which uses NeverRequire), this sample gates
// every tool call behind explicit user approval — a human-in-the-loop pattern.
AITool mcpTool = new HostedMcpServerTool(serverName: "microsoft_learn", serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire
};

// Create an agent with the MCP tool using Azure OpenAI Responses.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetResponsesClient(deploymentName)
    .AsIChatClient()
    .CreateAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgentWithApproval",
        tools: [mcpTool]);

await agent.RunAIAgentAsync();
