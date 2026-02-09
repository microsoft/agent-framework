// Copyright (c) Microsoft. All rights reserved.

// Hosted MCP Tools
// Use hosted MCP (Model Context Protocol) server tools with OpenAI Responses.
// The MCP tools are invoked server-side by the Responses API, not by the Agent Framework.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <hosted_mcp_auto>
// MCP tool with automatic approval — the tool is always called without user approval
var mcpTool = new HostedMcpServerTool(
    serverName: "microsoft_learn",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};

AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgent",
        tools: [mcpTool]);

AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Please summarize the Azure AI Agent documentation related to MCP Tool calling?", session));
// </hosted_mcp_auto>

// <hosted_mcp_approval>
// MCP tool with required approval
var mcpToolWithApproval = new HostedMcpServerTool(
    serverName: "microsoft_learn",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire
};

AIAgent agentWithApproval = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgentWithApproval",
        tools: [mcpToolWithApproval]);

AgentSession approvalSession = await agentWithApproval.CreateSessionAsync();
AgentResponse response = await agentWithApproval.RunAsync("Summarize the Azure AI Agent documentation?", approvalSession);
List<McpServerToolApprovalRequestContent> approvalRequests = response.Messages
    .SelectMany(m => m.Contents).OfType<McpServerToolApprovalRequestContent>().ToList();

while (approvalRequests.Count > 0)
{
    List<ChatMessage> userInputResponses = approvalRequests
        .ConvertAll(req =>
        {
            Console.WriteLine($"MCP Tool call: {req.ToolCall.ServerName}/{req.ToolCall.ToolName}. Reply Y to approve:");
            return new ChatMessage(ChatRole.User, [req.CreateResponse(Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
        });

    response = await agentWithApproval.RunAsync(userInputResponses, approvalSession);
    approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<McpServerToolApprovalRequestContent>().ToList();
}

Console.WriteLine($"\nAgent: {response}");
// </hosted_mcp_approval>
