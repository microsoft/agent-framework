// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("SHAREPOINT_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use SharePoint tools to assist users.
    Use the available SharePoint tools to answer questions and perform tasks.
    """;

// Create SharePoint tool options with project connection
var sharepointOptions = new SharePointGroundingToolOptions();
sharepointOptions.ProjectConnections.Add(new ToolProjectConnection(sharepointConnectionId));

FoundryVersionedAgent agent = await CreateAgentWithMEAIAsync();
// FoundryVersionedAgent agent = await CreateAgentWithNativeSDKAsync();

Console.WriteLine($"Created agent: {agent.Name}");

AgentResponse response = await agent.RunAsync("List the documents available in SharePoint");

// Display the response
Console.WriteLine("\n=== Agent Response ===");
Console.WriteLine(response);

// Display grounding annotations if any
foreach (var message in response.Messages)
{
    foreach (var content in message.Contents)
    {
        if (content.Annotations is not null)
        {
            foreach (var annotation in content.Annotations)
            {
                Console.WriteLine($"Annotation: {annotation}");
            }
        }
    }
}

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using FoundryAITool.CreateSharepointTool (MEAI + AgentFramework)
async Task<FoundryVersionedAgent> CreateAgentWithMEAIAsync()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        name: "SharePointAgent-MEAI",
        model: deploymentName,
        instructions: AgentInstructions,
        tools: [FoundryAITool.CreateSharepointTool(sharepointOptions)]);
}

// Option 2 - Using PromptAgentDefinition SDK native type
async Task<FoundryVersionedAgent> CreateAgentWithNativeSDKAsync()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        name: "SharePointAgent-NATIVE",
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { AgentTool.CreateSharepointTool(sharepointOptions) }
            })
    );
}
