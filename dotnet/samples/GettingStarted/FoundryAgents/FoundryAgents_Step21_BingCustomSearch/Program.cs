// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Bing Custom Search Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string connectionId = Environment.GetEnvironmentVariable("BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID is not set.");
string instanceName = Environment.GetEnvironmentVariable("BING_CUSTOM_SEARCH_INSTANCE_NAME") ?? throw new InvalidOperationException("BING_CUSTOM_SEARCH_INSTANCE_NAME is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use Bing Custom Search tools to assist users.
    Use the available Bing Custom Search tools to answer questions and perform tasks.
    """;
const string AgentName = "CustomSearchAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create the server side agent with Bing Custom Search tool
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: AgentName,
    creationOptions: new AgentVersionCreationOptions(
        new PromptAgentDefinition(model: deploymentName)
        {
            Instructions = AgentInstructions,
            Tools = {
                (ResponseTool)AgentTool.CreateBingCustomSearchTool(
                    new BingCustomSearchToolParameters([
                        new BingCustomSearchConfiguration(connectionId, instanceName)
                    ])
                ),
            }
        })
);

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a search query
AgentResponse response = await agent.RunAsync("Search for the latest news about Microsoft AI");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// Cleanup by deleting the agent
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine($"\nDeleted agent: {agent.Name}");
