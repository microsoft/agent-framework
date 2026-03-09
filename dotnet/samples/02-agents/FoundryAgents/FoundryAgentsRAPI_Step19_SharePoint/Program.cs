// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use SharePoint Grounding Tool with a FoundryAgentClient.

using Azure.AI.Projects.OpenAI;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_PROJECT_CONNECTION_ID") ?? throw new InvalidOperationException("SHAREPOINT_PROJECT_CONNECTION_ID is not set.");

const string AgentInstructions = """
    You are a helpful agent that can use SharePoint tools to assist users.
    Use the available SharePoint tools to answer questions and perform tasks.
    """;

// Create SharePoint tool options with project connection
var sharepointOptions = new SharePointGroundingToolOptions();
sharepointOptions.ProjectConnections.Add(new ToolProjectConnection(sharepointConnectionId));

// Create a FoundryResponsesAgent with SharePoint tool.
FoundryAgent agent = new(
    instructions: AgentInstructions,
    name: "SharePointAgent-RAPI",
    tools: [((ResponseTool)AgentTool.CreateSharepointTool(sharepointOptions)).AsAITool()]);

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
