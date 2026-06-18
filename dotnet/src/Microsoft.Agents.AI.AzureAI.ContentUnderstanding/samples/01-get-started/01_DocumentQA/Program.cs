// Copyright (c) Microsoft. All rights reserved.

// Document Q&A — PDF upload with CU-powered extraction.
//
// This sample demonstrates the simplest CU integration: upload a PDF and ask
// questions about it. Azure Content Understanding extracts structured markdown
// with table preservation — superior to LLM-only vision for scanned PDFs,
// handwritten content, and complex layouts.
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT              — Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME         — Model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Extensions.AI;

string projectEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set.");
string cuEndpoint = Environment.GetEnvironmentVariable("AZURE_CONTENTUNDERSTANDING_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

string pdfPath = Path.Combine(AppContext.BaseDirectory, "SampleAssets", "invoice.pdf");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();

// Set up the Azure Content Understanding context provider.
// MaxWait is infinite so this single-turn sample waits until CU analysis completes (mirrors the Python sample's max_wait=None).
await using var cu = new ContentUnderstandingContextProvider(
    new ContentUnderstandingContextProviderOptions(new Uri(cuEndpoint), credential)
    {
        AnalyzerId = "prebuilt-documentSearch", // RAG-optimized document analyzer
        MaxWait = Timeout.InfiniteTimeSpan,
    });

// Wire CU into a Foundry agent as a Context Provider.
AIProjectClient aiProjectClient = new(new Uri(projectEndpoint), credential);
AIAgent agent = aiProjectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "DocumentQA",
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions = "You are a helpful document analyst. Use the analyzed document "
            + "content and extracted fields to answer questions precisely.",
    },
    AIContextProviders = [cu],
});

// Turn 1: Upload PDF and ask a question.
// The CU provider extracts markdown + fields from the PDF and injects
// the full content into context so the agent can answer precisely.
Console.WriteLine("--- Upload PDF and ask questions ---");

byte[] pdfBytes = await File.ReadAllBytesAsync(pdfPath);
DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

ChatMessage userMessage = new(
    ChatRole.User,
    [
        new TextContent("What is this document about? Who is the vendor, and what is the total amount due?"),
        pdf,
    ]);

AgentResponse response = await agent.RunAsync(userMessage);
Console.WriteLine($"Agent: {response}");
