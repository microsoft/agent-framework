// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Responses as the backend, that uses a Hosted MCP Tool.
// In this case the OpenAI responses service will invoke any MCP tools as required. MCP tools are not invoked by the Agent Framework.
// The sample first shows how to use MCP tools with auto approval, and then how to set up a tool that requires approval before it can be invoked and how to approve such a tool.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// **** MCP Tool with Auto Approval ****
// *************************************

// Create an MCP tool definition that the agent can use.
// In this case we allow the tool to always be called without approval.
var mcpTool = new HostedMcpServerTool(
    serverName: "microsoft_learn",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};

// Create an agent based on Azure OpenAI Responses as the backend.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetOpenAIResponseClient(deploymentName)
     .CreateAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgent",
        tools: [mcpTool]);

// You can then invoke the agent like any other AIAgent.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Please summarize the Azure AI Agent documentation related to MCP Tool calling?", thread));

// **** MCP Tool with Approval Required ****
// *****************************************

// Create an MCP tool definition that the agent can use.
// In this case we require approval before the tool can be called.
var mcpToolWithApproval = new HostedMcpServerTool(
    serverName: "microsoft_learn",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire
};

// Create an agent based on Azure OpenAI Responses as the backend.
AIAgent agentWithRequiredApproval = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(
        instructions: "You answer questions by searching the Microsoft Learn content only.",
        name: "MicrosoftLearnAgentWithApproval",
        tools: [mcpToolWithApproval]);

// You can then invoke the agent like any other AIAgent.
var threadWithRequiredApproval = agentWithRequiredApproval.GetNewThread();
var response = await agentWithRequiredApproval.RunAsync("Please summarize the Azure AI Agent documentation related to MCP Tool calling?", threadWithRequiredApproval);
var userInputRequests = response.UserInputRequests.ToList();

while (userInputRequests.Count > 0)
{
    // Ask the user to approve each MCP call request.
    // For simplicity, we are assuming here that only MCP approval requests are being made.
    var userInputResponses = userInputRequests
        .OfType<McpServerToolApprovalRequestContent>()
        .Select(approvalRequest =>
        {
            Console.WriteLine($"""
                The agent would like to invoke the following MCP Tool, please reply Y to approve.
                ServerName: {approvalRequest.ToolCall.ServerName}
                Name: {approvalRequest.ToolCall.ToolName}
                Arguments: {string.Join(", ", approvalRequest.ToolCall.Arguments?.Select(x => $"{x.Key}: {x.Value}") ?? [])}
                """);
            return new ChatMessage(ChatRole.User, [approvalRequest.CreateResponse(Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
        })
        .ToList();

    // Pass the user input responses back to the agent for further processing.
    response = await agentWithRequiredApproval.RunAsync(userInputResponses, threadWithRequiredApproval);

    userInputRequests = response.UserInputRequests.ToList();
}

Console.WriteLine($"\nAgent: {response}");
