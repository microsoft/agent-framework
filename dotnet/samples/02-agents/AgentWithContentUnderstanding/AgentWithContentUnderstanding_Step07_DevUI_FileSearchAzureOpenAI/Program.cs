// Copyright (c) Microsoft. All rights reserved.

// DevUI File-Search Agent (Azure OpenAI backend) — CU extraction + file_search RAG.
//
// This sample hosts an Azure-OpenAI–backed agent behind the DevUI middleware
// and wires the Content Understanding provider with the `FileSearchConfig.FromOpenAI`
// backend. Upload large or multi-modal files in the browser; the provider:
//   1. extracts markdown via CU (handles scanned PDFs, audio, video),
//   2. uploads the extracted markdown to an Azure OpenAI vector store,
//   3. surfaces the file_search tool on the agent's context for token-efficient RAG.
//
// The vector store is auto-expiring (`expires_after = 1 day, last_active_at`) so
// inactive sample sessions are cleaned up automatically. The CU provider's
// DisposeAsync deletes the per-file uploads at app shutdown.
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/azure_openai_backend/agent.py
//
// Environment variables:
//   AZURE_OPENAI_ENDPOINT                  — Azure OpenAI endpoint URL
//   AZURE_OPENAI_DEPLOYMENT_NAME           — Chat-model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL
//
// Run:
//   dotnet run
// Then open https://localhost:50522/devui in a browser.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;
using OpenAI.VectorStores;

var builder = WebApplication.CreateBuilder(args);

string openAiEndpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? "gpt-4.1";
string cuEndpoint = builder.Configuration["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
var credential = new DefaultAzureCredential();

// 1. Build the Azure OpenAI client used both for chat and for vector store ops.
var azureOpenAIClient = new AzureOpenAIClient(new Uri(openAiEndpoint), credential);
var chatClient = azureOpenAIClient.GetChatClient(deploymentName).AsIChatClient();
builder.Services.AddChatClient(chatClient);

// 2. Create a vector store up-front (auto-expires after 1 day idle so abandoned
//    DevUI sessions don't accumulate storage cost). The CU provider uploads each
//    analyzed document into this store; the file_search tool reads from it.
var vectorStoreClient = azureOpenAIClient.GetVectorStoreClient();
var vectorStoreResult = await vectorStoreClient.CreateVectorStoreAsync(
    new VectorStoreCreationOptions
    {
        Name = "devui_cu_file_search",
        ExpirationPolicy = new VectorStoreExpirationPolicy(VectorStoreExpirationAnchor.LastActiveAt, days: 1),
    });
string vectorStoreId = vectorStoreResult.Value.Id;

// 3. Build the file_search tool that the agent will use to query the vector store.
HostedFileSearchTool fileSearchTool = new() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

// 4. CU provider with file_search wiring. Singleton — its lifecycle and any
//    background analyses span the lifetime of the web host. DisposeAsync runs
//    on app shutdown and deletes the files the provider uploaded.
builder.Services.AddSingleton(_ => new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        // 10 s combined budget for CU analysis + vector store upload.
        // Larger files (audio, video) will defer to background and resolve on the next turn.
        options.MaxWait = TimeSpan.FromSeconds(10);
        options.FileSearchConfig = FileSearchConfig.FromOpenAI(
            azureOpenAIClient,
            vectorStoreId,
            fileSearchTool);
    }));

const string agentName = "FileSearchDocAgent";

builder.AddAIAgent(agentName, (sp, key) =>
{
    var cu = sp.GetRequiredService<ContentUnderstandingContextProvider>();
    var client = sp.GetRequiredService<IChatClient>();
    return new ChatClientAgent(client, new ChatClientAgentOptions
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

Console.WriteLine($"DevUI is available at: https://localhost:50522/devui (vector store: {vectorStoreId})");
Console.WriteLine("OpenAI Responses API is available at: https://localhost:50522/v1/responses");
Console.WriteLine("Press Ctrl+C to stop the server.");

app.Run();
