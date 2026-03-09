// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Microsoft Fabric Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string fabricConnectionId = Environment.GetEnvironmentVariable("FABRIC_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("FABRIC_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = "You are a helpful assistant with access to Microsoft Fabric data. Answer questions based on data available through your Fabric connection.";

// Configure Microsoft Fabric tool options with project connection
var fabricToolOptions = new FabricDataAgentToolOptions();
fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection(fabricConnectionId));

FoundryVersionedAgent agent = await CreateAgentWithMEAIAsync();
// FoundryVersionedAgent agent = await CreateAgentWithNativeSDKAsync();

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a sample query
AgentResponse response = await agent.RunAsync("What data is available in the connected Fabric workspace?");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}

// Cleanup by deleting the agent
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using FoundryAITool wrapping for MicrosoftFabricTool (MEAI + AgentFramework)
async Task<FoundryVersionedAgent> CreateAgentWithMEAIAsync()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        name: "FabricAgent-MEAI",
        instructions: AgentInstructions,
        tools: [FoundryAITool.CreateMicrosoftFabricTool(fabricToolOptions)]);
}

// Option 2 - Using PromptAgentDefinition with AgentTool.CreateMicrosoftFabricTool (Native SDK)
async Task<FoundryVersionedAgent> CreateAgentWithNativeSDKAsync()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        name: "FabricAgent-NATIVE",
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools =
                {
                    AgentTool.CreateMicrosoftFabricTool(fabricToolOptions),
                }
            }));
}
