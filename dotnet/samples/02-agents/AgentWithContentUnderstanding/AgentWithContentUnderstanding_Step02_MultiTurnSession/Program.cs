// Copyright (c) Microsoft. All rights reserved.

// Multi-Turn Session — Cached results across turns.
//
// This sample demonstrates multi-turn document Q&A using an AgentSession.
// The session persists CU analysis results and conversation history across
// turns so the agent can answer follow-up questions about previously
// uploaded documents without re-analyzing them.
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/01-get-started/02_multi_turn_session.py
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

await using var cu = new ContentUnderstandingContextProvider(
    new Uri(cuEndpoint),
    credential,
    options =>
    {
        options.AnalyzerId = "prebuilt-documentSearch";
        options.MaxWait = TimeSpan.FromMinutes(2);
    });

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

// Create a persistent session — this keeps CU state and chat history across turns.
AgentSession session = await agent.CreateSessionAsync();

// Turn 1: Upload PDF.
// CU analyzes the PDF and injects full content into context.
Console.WriteLine("--- Turn 1: Upload PDF ---");
byte[] pdfBytes = await File.ReadAllBytesAsync(pdfPath);
DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

AgentResponse r1 = await agent.RunAsync(
    new ChatMessage(ChatRole.User, [new TextContent("What is this document about?"), pdf]),
    session);
Console.WriteLine($"Agent: {r1}\n");

// Turn 2: Unrelated question — no document needed; agent answers from general knowledge.
Console.WriteLine("--- Turn 2: Unrelated question ---");
AgentResponse r2 = await agent.RunAsync("What is the capital of France?", session);
Console.WriteLine($"Agent: {r2}\n");

// Turn 3: Detailed follow-up. The agent answers from the document content
// that was injected into conversation history in Turn 1. No re-analysis needed.
Console.WriteLine("--- Turn 3: Detailed follow-up ---");
AgentResponse r3 = await agent.RunAsync("What is the shipping address on the invoice?", session);
Console.WriteLine($"Agent: {r3}\n");
