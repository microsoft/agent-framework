// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Bing Custom Search Tool with AI Agents.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string connectionId = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID is not set.");
string instanceName = Environment.GetEnvironmentVariable("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME") ?? throw new InvalidOperationException("AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use Bing Custom Search tools to assist users.
    Use the available Bing Custom Search tools to answer questions and perform tasks.
    """;

// Create a Foundry project Responses API client.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient();

// Bing Custom Search tool parameters shared by both options
BingCustomSearchToolParameters bingCustomSearchToolParameters = new([
    new BingCustomSearchConfiguration(connectionId, instanceName)
]);

ChatClientAgent agent = CreateAgentWithMEAI();
// ChatClientAgent agent = CreateAgentWithNativeSDK();

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a search query
AgentResponse response = await agent.RunAsync("Search for the latest news about Microsoft AI");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// --- Agent Creation Options ---

#pragma warning disable CS8321 // Local function is declared but never used
// Option 1 - Using AsAITool wrapping for the ResponseTool returned by AgentTool.CreateBingCustomSearchTool (MEAI + AgentFramework)
ChatClientAgent CreateAgentWithMEAI()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "BingCustomSearchAgent-MEAI",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateBingCustomSearchTool(bingCustomSearchToolParameters)).AsAITool()]
        },
    });
}

// Option 2 - Using ResponseTool via AsAITool (Native SDK type)
ChatClientAgent CreateAgentWithNativeSDK()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "BingCustomSearchAgent-NATIVE",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateBingCustomSearchTool(bingCustomSearchToolParameters)).AsAITool()]
        },
    });
}
