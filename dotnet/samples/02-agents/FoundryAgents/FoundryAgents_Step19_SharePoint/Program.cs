// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("SHAREPOINT_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use SharePoint tools to assist users.
    Use the available SharePoint tools to answer questions and perform tasks.
    """;

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create SharePoint tool options with project connection
var sharepointOptions = new SharePointGroundingToolOptions();
sharepointOptions.ProjectConnections.Add(new ToolProjectConnection(sharepointConnectionId));

AIAgent agent = await CreateAgentWithMEAIAsync();
// AIAgent agent = await CreateAgentWithNativeSDKAsync();

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

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine($"\nDeleted agent: {agent.Name}");

// --- Agent Creation Options ---

// Option 1 - Using AgentTool.CreateSharepointTool + AsAITool() (MEAI + AgentFramework)
async Task<AIAgent> CreateAgentWithMEAIAsync()
{
    return await aiProjectClient.CreateAIAgentAsync(
        model: deploymentName,
        name: "SharePointAgent-MEAI",
        instructions: AgentInstructions,
        tools: [((ResponseTool)AgentTool.CreateSharepointTool(sharepointOptions)).AsAITool()]);
}

// Option 2 - Using PromptAgentDefinition SDK native type
async Task<AIAgent> CreateAgentWithNativeSDKAsync()
{
    return await aiProjectClient.CreateAIAgentAsync(
        name: "SharePointAgent-NATIVE",
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { AgentTool.CreateSharepointTool(sharepointOptions) }
            })
    );
}
