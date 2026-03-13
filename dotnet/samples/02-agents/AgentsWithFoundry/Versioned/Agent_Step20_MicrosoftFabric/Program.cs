// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Microsoft Fabric Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string fabricConnectionId = Environment.GetEnvironmentVariable("FABRIC_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("FABRIC_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = "You are a helpful assistant with access to Microsoft Fabric data. Answer questions based on data available through your Fabric connection.";

// Configure Microsoft Fabric tool options with project connection
var fabricToolOptions = new FabricDataAgentToolOptions();
fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection(fabricConnectionId));
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

ChatClientAgent agent = await CreateAgentWithMEAIAsync();
// ChatClientAgent agent = await CreateAgentWithNativeSDKAsync();

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a sample query
AgentResponse response = await agent.RunAsync("What data is available in the connected Fabric workspace?");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// Cleanup by deleting the agent
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using FoundryAITool wrapping for MicrosoftFabricTool (MEAI + AgentFramework)
async Task<ChatClientAgent> CreateAgentWithMEAIAsync()
{
    AITool tool = FoundryAITool.CreateMicrosoftFabricTool(fabricToolOptions);
    AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
        "FabricAgent-MEAI",
        new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool()! }
            }));

    return aiProjectClient.AsAIAgent(agentVersion);
}

// Option 2 - Using PromptAgentDefinition with AgentTool.CreateMicrosoftFabricTool (Native SDK)
async Task<ChatClientAgent> CreateAgentWithNativeSDKAsync()
{
    AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
        "FabricAgent-NATIVE",
        new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { AgentTool.CreateMicrosoftFabricTool(fabricToolOptions) }
            }));

    return aiProjectClient.AsAIAgent(agentVersion);
}
