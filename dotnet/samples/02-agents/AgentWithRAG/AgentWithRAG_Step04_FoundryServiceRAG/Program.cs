// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the built in RAG capabilities that the Foundry service provides when using AI Agents provided by Foundry.

using System.ClientModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Files;
using OpenAI.VectorStores;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create an AI Project client and get an OpenAI client that works with the foundry service.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(
    new Uri(endpoint),
    new DefaultAzureCredential());
OpenAIClient openAIClient = aiProjectClient.GetProjectOpenAIClient();

// Upload the file that contains the data to be used for RAG to the Foundry service.
OpenAIFileClient fileClient = openAIClient.GetOpenAIFileClient();
ClientResult<OpenAIFile> uploadResult = await fileClient.UploadFileAsync(
    filePath: "contoso-outdoors-knowledge-base.md",
    purpose: FileUploadPurpose.Assistants);

// Create a vector store in the Foundry service using the uploaded file.
VectorStoreClient vectorStoreClient = openAIClient.GetVectorStoreClient();
ClientResult<VectorStore> vectorStoreCreate = await vectorStoreClient.CreateVectorStoreAsync(options: new VectorStoreCreationOptions()
{
    Name = "contoso-outdoors-knowledge-base",
    FileIds = { uploadResult.Value.Id }
});

var fileSearchTool = new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreCreate.Value.Id)] };

AIAgent agent = await aiProjectClient
    .CreateAIAgentAsync(
        model: deploymentName,
        name: "AskContoso",
        instructions: "You are a helpful support specialist for Contoso Outdoors. Answer questions using the provided context and cite the source document when available.",
        tools: [fileSearchTool]);

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine(">> Asking about returns\n");
Console.WriteLine(await agent.RunAsync("Hi! I need help understanding the return policy.", session));

Console.WriteLine("\n>> Asking about shipping\n");
Console.WriteLine(await agent.RunAsync("How long does standard shipping usually take?", session));

Console.WriteLine("\n>> Asking about product care\n");
Console.WriteLine(await agent.RunAsync("What is the best way to maintain the TrailRunner tent fabric?", session));

// Cleanup
await fileClient.DeleteFileAsync(uploadResult.Value.Id);
await vectorStoreClient.DeleteVectorStoreAsync(vectorStoreCreate.Value.Id);
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
