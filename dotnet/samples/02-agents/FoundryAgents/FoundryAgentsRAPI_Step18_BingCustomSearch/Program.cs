// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Bing Custom Search Tool with a FoundryAgentClient.

using Azure.AI.Projects.OpenAI;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string connectionId = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID is not set.");
string instanceName = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use Bing Custom Search tools to assist users.
    Use the available Bing Custom Search tools to answer questions and perform tasks.
    """;

// Bing Custom Search tool parameters
BingCustomSearchToolParameters bingCustomSearchToolParameters = new([
    new BingCustomSearchConfiguration(connectionId, instanceName)
]);

// Create a FoundryResponsesAgent with Bing Custom Search tool.
FoundryAgent agent = new(
    instructions: AgentInstructions,
    name: "BingCustomSearchAgent-RAPI",
    tools: [((ResponseTool)AgentTool.CreateBingCustomSearchTool(bingCustomSearchToolParameters)).AsAITool()]);

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a search query
AgentResponse response = await agent.RunAsync("Search for the latest news about Microsoft AI");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}
