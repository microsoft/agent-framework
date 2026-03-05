// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Foundry tools (MCP and code interpreter)
// with an AI agent hosted using the Azure AI AgentServer SDK.

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var toolConnectionId = Environment.GetEnvironmentVariable("MCP_TOOL_CONNECTION_ID") ?? throw new InvalidOperationException("MCP_TOOL_CONNECTION_ID is not set.");

var credential = new AzureCliCredential();

var chatClient = new AzureOpenAIClient(new Uri(openAiEndpoint), credential)
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .UseFoundryTools(new { type = "mcp", project_connection_id = toolConnectionId }, new { type = "code_interpreter" })
    .UseOpenTelemetry(sourceName: "Agents", configure: (cfg) => cfg.EnableSensitiveData = true)
    .Build();

var agent = new ChatClientAgent(chatClient,
      name: "AgentWithTools",
      instructions: @"You are a helpful assistant with access to tools for fetching Microsoft documentation.

  IMPORTANT: When the user asks about Microsoft Learn articles or documentation:
  1. You MUST use the microsoft_docs_fetch tool to retrieve the actual content
  2. Do NOT rely on your training data
  3. Always fetch the latest information from the provided URL

  Available tools:
  - microsoft_docs_fetch: Fetches and converts Microsoft Learn documentation
  - microsoft_docs_search: Searches Microsoft/Azure documentation
  - microsoft_code_sample_search: Searches for code examples")
      .AsBuilder()
      .UseOpenTelemetry(sourceName: "Agents", configure: (cfg) => cfg.EnableSensitiveData = true)
      .Build();

await agent.RunAIAgentAsync(telemetrySourceName: "Agents");
