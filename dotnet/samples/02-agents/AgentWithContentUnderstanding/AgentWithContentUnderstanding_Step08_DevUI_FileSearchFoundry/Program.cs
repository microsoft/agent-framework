// Copyright (c) Microsoft. All rights reserved.

// DevUI File-Search Agent (Foundry backend) — CU extraction + file_search RAG via Foundry.
//
// This sample hosts a Foundry-backed agent behind the DevUI middleware and
// wires the Content Understanding provider with the `FileSearchConfig.FromFoundry`
// backend. Upload large or multi-modal files in the browser; the provider:
//   1. extracts markdown via CU (handles scanned PDFs, audio, video),
//   2. uploads the extracted markdown to a Foundry vector store,
//   3. surfaces the file_search tool on the agent's context for token-efficient RAG.
//
// The vector store is created up-front and deleted at app shutdown. The CU
// provider's DisposeAsync deletes the per-file uploads it owned (the store
// stays under caller ownership).
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/foundry_backend/agent.py
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT              — Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME         — Model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL
//
// Run:
//   dotnet run
// Then open https://localhost:50524/devui in a browser.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

string projectEndpoint = builder.Configuration["AZURE_AI_PROJECT_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_AI_MODEL_DEPLOYMENT_NAME"] ?? "gpt-4.1";
string cuEndpoint = builder.Configuration["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
var credential = new DefaultAzureCredential();
var aiProjectClient = new AIProjectClient(new Uri(projectEndpoint), credential);

// 1. Create a Foundry vector store up-front. The CU provider uploads each
//    analyzed document into this store; the file_search tool reads from it.
var projectOpenAIClient = aiProjectClient.GetProjectOpenAIClient();
var vectorStoresClient = projectOpenAIClient.GetProjectVectorStoresClient();
var vectorStoreResult = await vectorStoresClient.CreateVectorStoreAsync(
    options: new() { Name = "devui_cu_foundry_file_search" });
string vectorStoreId = vectorStoreResult.Value.Id;

// 2. Build the file_search tool that the agent will use to query the vector store.
HostedFileSearchTool fileSearchTool = new() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

// 3. CU provider with file_search wiring. Singleton — its lifecycle spans the
//    web host. DisposeAsync runs on app shutdown and deletes the files the
//    provider uploaded; the vector store is deleted explicitly below.
builder.Services.AddSingleton(_ => new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        // 10 s combined budget for CU analysis + vector store upload.
        // Larger files (audio, video) will defer to background and resolve on the next turn.
        options.MaxWait = TimeSpan.FromSeconds(10);
        options.FileSearchConfig = FileSearchConfig.FromFoundry(
            aiProjectClient,
            vectorStoreId,
            fileSearchTool);
    }));

const string agentName = "FoundryFileSearchDocAgent";

builder.AddAIAgent(agentName, (sp, key) =>
{
    var cu = sp.GetRequiredService<ContentUnderstandingContextProvider>();
    return aiProjectClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = key,
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful document analysis assistant with RAG capabilities. "
                + "When a user uploads files, they are automatically analyzed using Azure Content Understanding "
                + "and indexed in a vector store for efficient retrieval. "
                + "Analysis takes time (seconds for documents, longer for audio/video) — if a document "
                + "is still pending, let the user know and suggest they ask again shortly. "
                + "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
                + "Multiple files can be uploaded and queried in the same conversation. "
                + "When answering, cite specific content from the documents.",
        },
        AIContextProviders = [cu],
    });
});

builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

var app = builder.Build();

app.MapOpenAIResponses();
app.MapOpenAIConversations();

if (builder.Environment.IsDevelopment())
{
    app.MapDevUI();
}

// Delete the vector store at app shutdown (the CU provider's DisposeAsync
// already cleans up the per-file uploads).
app.Lifetime.ApplicationStopping.Register(() =>
{
    try
    {
        vectorStoresClient.DeleteVectorStore(vectorStoreId);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Vector store cleanup failed: {ex.Message}");
    }
});

Console.WriteLine($"DevUI is available at: https://localhost:50524/devui (vector store: {vectorStoreId})");
Console.WriteLine("OpenAI Responses API is available at: https://localhost:50524/v1/responses");
Console.WriteLine("Press Ctrl+C to stop the server.");

app.Run();
