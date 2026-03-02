// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Microsoft Fabric Tool with AI Agents.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string fabricConnectionId = Environment.GetEnvironmentVariable("FABRIC_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("FABRIC_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = "You are a helpful assistant with access to Microsoft Fabric data. Answer questions based on data available through your Fabric connection.";

// Create a Foundry project Responses API client.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient();

// Configure Microsoft Fabric tool options with project connection
var fabricToolOptions = new FabricDataAgentToolOptions();
fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection(fabricConnectionId));

ChatClientAgent agent = CreateAgentWithMEAI();
// ChatClientAgent agent = CreateAgentWithNativeSDK();

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a sample query
AgentResponse response = await agent.RunAsync("What data is available in the connected Fabric workspace?");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// --- Agent Creation Options ---

#pragma warning disable CS8321 // Local function is declared but never used
// Option 1 - Using AsAITool wrapping for the ResponseTool returned by AgentTool.CreateMicrosoftFabricTool (MEAI + AgentFramework)
ChatClientAgent CreateAgentWithMEAI()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "FabricAgent-MEAI",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateMicrosoftFabricTool(fabricToolOptions)).AsAITool()]
        },
    });
}

// Option 2 - Using ResponseTool via AsAITool (Native SDK type)
ChatClientAgent CreateAgentWithNativeSDK()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "FabricAgent-NATIVE",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateMicrosoftFabricTool(fabricToolOptions)).AsAITool()]
        },
    });
}
