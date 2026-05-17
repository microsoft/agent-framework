// Copyright (c) Microsoft. All rights reserved.

// Multi-Modal Chat — PDF, audio, and video in a single turn.
//
// This sample demonstrates CU's multi-modal capability: upload a PDF invoice,
// an audio call recording, and a video file all at once. The provider analyzes
// all three in parallel using the right CU analyzer for each media type.
//
// The provider auto-detects the media type and selects the right CU analyzer:
//   PDF/images  → prebuilt-documentSearch
//   Audio       → prebuilt-audioSearch
//   Video       → prebuilt-videoSearch
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/01-get-started/03_multimodal_chat.py
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT              — Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME         — Model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL

using System.Diagnostics;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Extensions.AI;

string projectEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4.1";
string cuEndpoint = Environment.GetEnvironmentVariable("AZURE_CONTENTUNDERSTANDING_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

string pdfPath = Path.Combine(AppContext.BaseDirectory, "SampleAssets", "invoice.pdf");

// Public audio/video from the Azure Content Understanding samples repo.
const string CuAssets = "https://raw.githubusercontent.com/Azure-Samples/azure-ai-content-understanding-assets/main";
string audioUrl = $"{CuAssets}/audio/callCenterRecording.mp3";
string videoUrl = $"{CuAssets}/videos/sdk_samples/FlightSimulator.mp4";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();

// No AnalyzerId specified — the provider auto-detects from each attachment's media type:
//   PDF/images → prebuilt-documentSearch
//   Audio      → prebuilt-audioSearch
//   Video      → prebuilt-videoSearch
await using var cu = new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        options.MaxWait = TimeSpan.FromMinutes(5); // audio + video may take a while
    });

AIProjectClient aiProjectClient = new(new Uri(projectEndpoint), credential);
AIAgent agent = aiProjectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "MultiModalAgent",
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions = "You are a helpful assistant that can analyze documents, audio, "
            + "and video files. Answer questions using the extracted content.",
    },
    AIContextProviders = [cu],
});

AgentSession session = await agent.CreateSessionAsync();

// Turn 1: Upload PDF + audio + video together — they analyze in parallel.
const string Turn1Prompt =
    "I'm uploading three files: an invoice PDF, a call center audio recording, "
    + "and a flight simulator video. Give a brief summary of each file.";

Console.WriteLine("--- Turn 1: Upload PDF + audio + video (parallel analysis) ---");
Console.WriteLine("  (CU analysis may take a few minutes for these audio/video files...)");
Console.WriteLine($"User: {Turn1Prompt}");

byte[] pdfBytes = await File.ReadAllBytesAsync(pdfPath);
DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

UriContent audio = new(audioUrl, "audio/mp3")
{
    AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "callCenterRecording.mp3" },
};
UriContent video = new(videoUrl, "video/mp4")
{
    AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "FlightSimulator.mp4" },
};

var stopwatch = Stopwatch.StartNew();
AgentResponse r1 = await agent.RunAsync(
    new ChatMessage(ChatRole.User, [new TextContent(Turn1Prompt), pdf, audio, video]),
    session);
stopwatch.Stop();
Console.WriteLine($"  [Analyzed in {stopwatch.Elapsed.TotalSeconds:F1}s]");
Console.WriteLine($"Agent: {r1}\n");

// Turn 2: PDF detail.
Console.WriteLine("--- Turn 2: PDF detail ---");
AgentResponse r2 = await agent.RunAsync("What are the line items and their amounts on the invoice?", session);
Console.WriteLine($"Agent: {r2}\n");

// Turn 3: Audio detail.
Console.WriteLine("--- Turn 3: Audio detail ---");
AgentResponse r3 = await agent.RunAsync("What was the customer's issue in the call recording?", session);
Console.WriteLine($"Agent: {r3}\n");

// Turn 4: Video detail.
Console.WriteLine("--- Turn 4: Video detail ---");
AgentResponse r4 = await agent.RunAsync("What key scenes or actions are shown in the flight simulator video?", session);
Console.WriteLine($"Agent: {r4}\n");

// Turn 5: Cross-document question.
Console.WriteLine("--- Turn 5: Cross-document question ---");
AgentResponse r5 = await agent.RunAsync(
    "Across all three files, which one contains financial data, which one involves a "
        + "customer interaction, and which one is a visual demonstration?",
    session);
Console.WriteLine($"Agent: {r5}\n");
