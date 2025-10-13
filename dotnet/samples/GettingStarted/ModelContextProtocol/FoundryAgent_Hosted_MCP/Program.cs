// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure Foundry Agents as the backend.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";

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
    name: "MicrosoftLearnAgent",
    instructions: "You answer questions by searching the Microsoft Learn content only.",
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
var response = await agent.RunAsync("Please summarize the Azure AI Agent documentation related to MCP Tool calling?", thread, runOptions);
Console.WriteLine(response);

// Cleanup for sample purposes.
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
