// Copyright (c) Microsoft. All rights reserved.

// DevUI Multi-Modal Agent — file upload + CU-powered analysis through the DevUI web UI.
//
// This sample hosts a Foundry-backed agent in an ASP.NET Core app and exposes
// it via the DevUI middleware. Users upload PDFs, scanned documents, handwritten
// images, audio, or video, and the Content Understanding context provider
// automatically analyzes them and injects the rendered markdown + fields into
// the LLM context.
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/02-devui/01-multimodal_agent/agent.py
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT              — Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME         — Model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL
//
// Run:
//   dotnet run
// Then open https://localhost:50520/devui in a browser.

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
// In production, prefer a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency from credential probing and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();
var aiProjectClient = new AIProjectClient(new Uri(projectEndpoint), credential);

// The CU provider is a singleton so its session state and any background analyses
// survive across HTTP requests. DisposeAsync runs at app shutdown.
builder.Services.AddSingleton(_ => new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        // For interactive DevUI use, a short timeout keeps the chat responsive —
        // the agent tells the user the file is still being analyzed and resolves
        // it on the next turn.
        options.MaxWait = TimeSpan.FromSeconds(5);
    }));

const string agentName = "MultiModalDocAgent";

builder.AddAIAgent(agentName, (sp, key) =>
{
    var cu = sp.GetRequiredService<ContentUnderstandingContextProvider>();
    return aiProjectClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = key,
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful document analysis assistant. "
                + "When a user uploads files, they are automatically analyzed using Azure Content Understanding. "
                + "Use list_documents() to check which documents are ready, pending, or failed "
                + "and to see which files are available for answering questions. "
                + "Tell the user if any documents are still being analyzed. "
                + "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
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

Console.WriteLine("DevUI is available at: https://localhost:50520/devui");
Console.WriteLine("OpenAI Responses API is available at: https://localhost:50520/v1/responses");
Console.WriteLine("Press Ctrl+C to stop the server.");

app.Run();
