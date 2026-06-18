// Copyright (c) Microsoft. All rights reserved.

// Invoice Processing — Structured output with prebuilt-invoice analyzer.
//
// This sample demonstrates CU's structured field extraction combined with the
// agent. The prebuilt-invoice analyzer extracts typed fields (VendorName,
// InvoiceTotal, DueDate, LineItems, etc.) with confidence scores. We use
// OutputSections=Fields (no markdown) since we want the LLM to produce a
// structured response from the extracted fields, not summarize document text.
//
// The provider currently exposes only a global
// ContentUnderstandingContextProviderOptions.AnalyzerId; per-attachment
// analyzer overrides are not yet supported. For this single-attachment
// sample, the global setting is equivalent. See README.md.
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

// Use the prebuilt-invoice analyzer for typed field extraction.
// OutputSections = Fields means only the CU "fields" block is rendered into the
// LLM context — no document markdown — because we want the structured fields,
// not raw text.
await using var cu = new ContentUnderstandingContextProvider(
    new ContentUnderstandingContextProviderOptions(new Uri(cuEndpoint), credential)
    {
        AnalyzerId = "prebuilt-invoice",
        OutputSections = AnalysisSection.Fields,
        MaxWait = Timeout.InfiniteTimeSpan, // wait until CU analysis finishes (mirrors Python max_wait=None)
    });

AIProjectClient aiProjectClient = new(new Uri(projectEndpoint), credential);
AIAgent agent = aiProjectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "InvoiceProcessor",
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions =
            "You are an invoice processing assistant. Extract invoice data from the "
            + "provided CU fields (JSON-like text with confidence scores). Return the "
            + "extracted vendor name, total amount, currency, due date, and line items "
            + "as plain-text key: value pairs (one per line). Flag any field whose "
            + "confidence is below 0.8 under a 'Low confidence:' heading.",
    },
    AIContextProviders = [cu],
});

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("--- Upload Invoice (Structured Field Extraction) ---");
byte[] pdfBytes = await File.ReadAllBytesAsync(pdfPath);
DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

AgentResponse r1 = await agent.RunAsync(
    new ChatMessage(
        ChatRole.User,
        [
            new TextContent("Process this invoice. Extract the vendor name, total amount, due date, and all line items."),
            pdf,
        ]),
    session);
Console.WriteLine($"Agent:\n{r1}\n");

// Follow-up: free-text question about the invoice.
Console.WriteLine("--- Follow-up (Free Text) ---");
AgentResponse r2 = await agent.RunAsync(
    "What is the payment term? Are there any fields with low confidence?",
    session);
Console.WriteLine($"Agent: {r2}\n");
