// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with a ChatClientAgent.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;

string sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("SHAREPOINT_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use SharePoint tools to assist users.
    Use the available SharePoint tools to answer questions and perform tasks.
    """;

// Create SharePoint tool options with project connection
var sharepointOptions = new SharePointGroundingToolOptions();
sharepointOptions.ProjectConnections.Add(new ToolProjectConnection(sharepointConnectionId));

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a AIAgent with SharePoint tool.
AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: AgentInstructions,
    name: "SharePointAgent-RAPI",
    tools: [FoundryAITool.CreateSharepointTool(sharepointOptions)]);

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
