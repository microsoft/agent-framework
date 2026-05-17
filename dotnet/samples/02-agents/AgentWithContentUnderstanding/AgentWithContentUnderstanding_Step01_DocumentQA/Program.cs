// Copyright (c) Microsoft. All rights reserved.

// Document Q&A — PDF upload with CU-powered extraction.
//
// This sample demonstrates the simplest CU integration: upload a PDF and ask
// questions about it. Azure Content Understanding extracts structured markdown
// with table preservation — superior to LLM-only vision for scanned PDFs,
// handwritten content, and complex layouts.
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/01-get-started/01_document_qa.py
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
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4.1";
string cuEndpoint = Environment.GetEnvironmentVariable("AZURE_CONTENTUNDERSTANDING_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

string pdfPath = Path.Combine(AppContext.BaseDirectory, "SampleAssets", "invoice.pdf");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();

// Set up the Azure Content Understanding context provider.
// MaxWait set high so analysis completes inline for this single-turn sample (no background deferral).
await using var cu = new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        options.AnalyzerId = "prebuilt-documentSearch"; // RAG-optimized document analyzer
        options.MaxWait = TimeSpan.FromMinutes(2);
    });

// Wire CU into a Foundry agent.
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
