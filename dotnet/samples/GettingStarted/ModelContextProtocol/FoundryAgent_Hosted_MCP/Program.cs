// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using System;
using System.Collections.Generic;
using System.Threading;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";

const string AgentName = "MicrosoftLearnAgent";
const string AgentInstructions = "You answer questions by searching the Microsoft Learn content only.";

// Get a client to create/retrieve server side agents with.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create an MCP tool definition that the agent can use.
var mcpTool = new MCPToolDefinition(
    serverLabel: "microsoft_learn",
    serverUrl: "https://learn.microsoft.com/api/mcp");
mcpTool.AllowedTools.Add("microsoft_docs_search");

// Create a server side persistent agent with the Azure.AI.Agents.Persistent SDK.
var agentMetadata = await persistentAgentsClient.Administration.CreateAgentAsync(
    model: model,
    name: AgentName,
    instructions: AgentInstructions,
    tools: [mcpTool]);

// Retrieve an already created server side persistent agent as an AIAgent.
AIAgent agent = await persistentAgentsClient.GetAIAgentAsync(agentMetadata.Value.Id);

// Create run options to configure the agent invocation.
var runOptions = new ChatClientAgentRunOptions()
{
    ChatOptions = new()
    {
        RawRepresentationFactory = (_) => new ThreadAndRunOptions()
        {
            ToolResources = new MCPToolResource(serverLabel: "microsoft_learn")
            {
                RequireApproval = new MCPApproval("never"),
            }.ToToolResources()
        }
    }
};

// You can then invoke the agent like any other AIAgent.
AgentThread thread = agent.GetNewThread();
var response = await agent.RunAsync("Please summarize the Azure AI Agent documentation realted to MCP Tool calling?", thread, runOptions);
Console.WriteLine(response);

// Cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

/*
PersistentAgentThread thread = persistentAgentsClient.Threads.CreateThread();

// Create message to thread
persistentAgentsClient.Messages.CreateMessage(
    thread.Id,
    MessageRole.User,
    "Please summarize the Azure REST API specifications Readme and give the basic information on TypeSpec.");

// By default all the tools require approvals. To set the absolute trust for the tool please uncomment the
// next code.
// mcpToolResource.RequireApproval = new MCPApproval("never");
// If using multiple tools it is possible to set the trust per tool.
// var mcpApprovalPerTool = new MCPApprovalPerTool()
// {
//     Always= new MCPToolList(["non_trusted_tool1", "non_trusted_tool2"]),
//     Never = new MCPToolList(["trusted_tool1", "trusted_tool2"]),
// };
// mcpToolResource.RequireApproval = new MCPApproval(perToolApproval: mcpApprovalPerTool);
// Note: This functionality is available since version 1.2.0-beta.4.
// In older versions please use serialization into binary object as discussed in the issue
// https://github.com/Azure/azure-sdk-for-net/issues/52213

// Run the agent with MCP tool resources
ThreadRun run = persistentAgentsClient.Runs.CreateRun(thread, agentMetadata, mcpToolResource.ToToolResources());

// Handle run execution and tool approvals
while (run.Status == RunStatus.Queued || run.Status == RunStatus.InProgress || run.Status == RunStatus.RequiresAction)
{
    Thread.Sleep(TimeSpan.FromMilliseconds(1000));
    run = persistentAgentsClient.Runs.GetRun(thread.Id, run.Id);

    if (run.Status == RunStatus.RequiresAction && run.RequiredAction is SubmitToolApprovalAction toolApprovalAction)
    {
        var toolApprovals = new List<ToolApproval>();
        foreach (var toolCall in toolApprovalAction.SubmitToolApproval.ToolCalls)
        {
            if (toolCall is RequiredMcpToolCall mcpToolCall)
            {
                Console.WriteLine($"Approving MCP tool call: {mcpToolCall.Name}, Arguments: {mcpToolCall.Arguments}");
                toolApprovals.Add(new ToolApproval(mcpToolCall.Id, approve: true)
                {
                    Headers = { ["SuperSecret"] = "123456" }
                });
            }
        }

        if (toolApprovals.Count > 0)
        {
            run = persistentAgentsClient.Runs.SubmitToolOutputsToRun(thread.Id, run.Id, toolApprovals: toolApprovals);
        }
    }
}

Console.WriteLine(run.Status);

IReadOnlyList<PersistentThreadMessage> messages = [..persistentAgentsClient.Messages.GetMessages(
    threadId: thread.Id,
    order: ListSortOrder.Ascending
)];

foreach (PersistentThreadMessage threadMessage in messages)
{
    Console.Write($"{threadMessage.CreatedAt:yyyy-MM-dd HH:mm:ss} - {threadMessage.Role,10}: ");
    foreach (MessageContent contentItem in threadMessage.ContentItems)
    {
        if (contentItem is MessageTextContent textItem)
        {
            Console.Write(textItem.Text);
        }
        else if (contentItem is MessageImageFileContent imageFileItem)
        {
            Console.Write($"<image from ID: {imageFileItem.FileId}>");
        }
        Console.WriteLine();
    }
}
*/
