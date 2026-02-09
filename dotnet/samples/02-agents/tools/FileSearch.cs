// Copyright (c) Microsoft. All rights reserved.

// File Search Tool
// Use a hosted file search tool to find relevant documents.
// Note: File search is typically available via Azure AI Foundry or OpenAI Assistants.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// <file_search>
// Create an agent with file search capability
// Note: You must first upload files and create a vector store in Azure AI Foundry
var vectorStoreId = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_VECTOR_STORE_ID")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_VECTOR_STORE_ID is not set.");

AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "FileSearchAgent",
    creationOptions: new AgentVersionCreationOptions(
        new PromptAgentDefinition(model: deploymentName)
        {
            Instructions = "You are a helpful assistant that answers questions based on uploaded documents.",
            Tools = { ResponseTool.CreateFileSearchTool([vectorStoreId]) }
        }));

Console.WriteLine(await agent.RunAsync("What are the key findings in the uploaded document?"));
// </file_search>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
