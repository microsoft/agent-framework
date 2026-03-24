// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

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
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

FoundryAgent agent = await CreateAgentWithMEAIAsync();
// FoundryAgent agent = await CreateAgentWithNativeSDKAsync();

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
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using FoundryAITool.CreateSharepointTool (MEAI + AgentFramework)
async Task<FoundryAgent> CreateAgentWithMEAIAsync()
{
    AITool tool = FoundryAITool.CreateSharepointTool(sharepointOptions);
    AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
        "SharePointAgent-MEAI",
        new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool()! }
            }));

    return aiProjectClient.AsAIAgent(agentVersion);
}

// Option 2 - Using PromptAgentDefinition SDK native type
async Task<FoundryAgent> CreateAgentWithNativeSDKAsync()
{
    AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
        "SharePointAgent-NATIVE",
        new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { AgentTool.CreateSharepointTool(sharepointOptions) }
            }));

    return aiProjectClient.AsAIAgent(agentVersion);
}
