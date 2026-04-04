// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Microsoft Fabric Tool with a ChatClientAgent.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;

string fabricConnectionId = Environment.GetEnvironmentVariable("FABRIC_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("FABRIC_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = "You are a helpful assistant with access to Microsoft Fabric data. Answer questions based on data available through your Fabric connection.";

// Configure Microsoft Fabric tool options with project connection
var fabricToolOptions = new FabricDataAgentToolOptions();
fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection(fabricConnectionId));

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a AIAgent with Microsoft Fabric tool.
AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: AgentInstructions,
    name: "FabricAgent-RAPI",
    tools: [FoundryAITool.CreateMicrosoftFabricTool(fabricToolOptions)]);

Console.WriteLine($"Created agent: {agent.Name}");

// Run the agent with a sample query
AgentResponse response = await agent.RunAsync("What data is available in the connected Fabric workspace?");

Console.WriteLine("\n=== Agent Response ===");
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Text);
}
