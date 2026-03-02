// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with AI Agents.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("SHAREPOINT_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use SharePoint tools to assist users.
    Use the available SharePoint tools to answer questions and perform tasks.
    """;

// Create a Foundry project Responses API client.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient();

// Create SharePoint tool options with project connection
var sharepointOptions = new SharePointGroundingToolOptions();
sharepointOptions.ProjectConnections.Add(new ToolProjectConnection(sharepointConnectionId));

ChatClientAgent agent = CreateAgentWithMEAI();
// ChatClientAgent agent = CreateAgentWithNativeSDK();

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

// --- Agent Creation Options ---

#pragma warning disable CS8321 // Local function is declared but never used
// Option 1 - Using AgentTool.CreateSharepointTool + AsAITool() (MEAI + AgentFramework)
ChatClientAgent CreateAgentWithMEAI()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "SharePointAgent-MEAI",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateSharepointTool(sharepointOptions)).AsAITool()]
        },
    });
}

// Option 2 - Using ResponseTool via AsAITool (Native SDK type)
ChatClientAgent CreateAgentWithNativeSDK()
{
    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "SharePointAgent-NATIVE",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AgentInstructions,
            Tools = [((ResponseTool)AgentTool.CreateSharepointTool(sharepointOptions)).AsAITool()]
        },
    });
}
