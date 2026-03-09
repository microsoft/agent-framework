// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Bing Custom Search Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string connectionId = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID is not set.");
string instanceName = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use Bing Custom Search tools to assist users.
    Use the available Bing Custom Search tools to answer questions and perform tasks.
    """;

// Bing Custom Search tool parameters shared by both options
BingCustomSearchToolOptions bingCustomSearchToolParameters = new([
    new BingCustomSearchConfiguration(connectionId, instanceName)
]);

FoundryVersionedAgent agent = await CreateAgentWithMEAIAsync();
// AIAgent agent = await CreateAgentWithNativeSDKAsync();

AIProjectClient aiProjectClient = agent.GetService<AIProjectClient>()!;

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a search query
AgentResponse response = await agent.RunAsync("Search for the latest news about Microsoft AI");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// Cleanup by deleting the agent
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using FoundryAITool wrapping for BingCustomSearchTool (MEAI + AgentFramework)
async Task<FoundryVersionedAgent> CreateAgentWithMEAIAsync()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        name: "BingCustomSearchAgent-MEAI",
        instructions: AgentInstructions,
        tools: [FoundryAITool.CreateBingCustomSearchTool(bingCustomSearchToolParameters)]);
}

// Option 2 - Using PromptAgentDefinition with AgentTool.CreateBingCustomSearchTool (Native SDK)
async Task<AIAgent> CreateAgentWithNativeSDKAsync()
{
    return await aiProjectClient.CreateAIAgentAsync(
        name: "BingCustomSearchAgent-NATIVE",
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = {
                    (ResponseTool)AgentTool.CreateBingCustomSearchTool(bingCustomSearchToolParameters),
                }
            })
    );
}
