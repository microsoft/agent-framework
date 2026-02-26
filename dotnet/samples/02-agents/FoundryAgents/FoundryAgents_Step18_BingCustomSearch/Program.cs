// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Bing Custom Search Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string connectionId = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID is not set.");
string instanceName = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use Bing Custom Search tools to assist users.
    Use the available Bing Custom Search tools to answer questions and perform tasks.
    """;

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Bing Custom Search tool parameters shared by both options
BingCustomSearchToolParameters bingCustomSearchToolParameters = new([
    new BingCustomSearchConfiguration(connectionId, instanceName)
]);

AIAgent agent = await CreateAgentWithMEAIAsync();
// AIAgent agent = await CreateAgentWithNativeSDKAsync();

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

// --- Agent Creation Options ---

// Option 1 - Using AsAITool wrapping for the ResponseTool returned by AgentTool.CreateBingCustomSearchTool (MEAI + AgentFramework)
async Task<AIAgent> CreateAgentWithMEAIAsync()
{
    return await aiProjectClient.CreateAIAgentAsync(
        model: deploymentName,
        name: "BingCustomSearchAgent-MEAI",
        instructions: AgentInstructions,
        tools: [((ResponseTool)AgentTool.CreateBingCustomSearchTool(bingCustomSearchToolParameters)).AsAITool()]);
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
