// Copyright (c) Microsoft. All rights reserved.

// Large Doc + file_search RAG — CU extraction + Foundry vector store.
//
// For large documents (100+ pages) or long audio/video, injecting the full
// CU-extracted content into the LLM context is impractical. This sample shows
// how to use the built-in file_search integration: CU extracts markdown and
// the provider automatically uploads it to a Foundry/OpenAI vector store for
// token-efficient RAG. The agent then queries the vector store via the
// file_search tool that the provider surfaces.
//
// When FileSearchConfig is provided, the provider:
//   1. Extracts markdown via CU (handles scanned PDFs, audio, video)
//   2. Uploads the extracted markdown to the vector store
//   3. Surfaces the file_search tool on the agent's context
//   4. Cleans up uploaded files on DisposeAsync (the vector store itself
//      is caller-owned and is deleted explicitly below).
//
// Mirrors the Python sample at:
//   python/packages/azure-contentunderstanding/samples/01-get-started/05_large_doc_file_search.py
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

AIProjectClient aiProjectClient = new(new Uri(projectEndpoint), credential);
var projectOpenAIClient = aiProjectClient.GetProjectOpenAIClient();
var vectorStoresClient = projectOpenAIClient.GetProjectVectorStoresClient();

// 1. Create an empty vector store for this run. The CU provider will upload
//    the extracted markdown into it.
Console.WriteLine("--- Creating Foundry vector store ---");
var vectorStoreResult = await vectorStoresClient.CreateVectorStoreAsync(
    options: new() { Name = "cu_large_doc_demo" });
string vectorStoreId = vectorStoreResult.Value.Id;
Console.WriteLine($"  Vector store id: {vectorStoreId}");

try
{
    // 2. Build the file_search tool that the agent will use to query the vector store.
    HostedFileSearchTool fileSearchTool = new() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

    // 3. Configure CU with file_search integration. The provider:
    //    - extracts markdown via CU
    //    - uploads it to vectorStoreId via the configured backend
    //    - surfaces the file_search tool on the agent's context.
    await using var cu = new ContentUnderstandingContextProvider(
        new Uri(cuEndpoint),
        credential,
        options =>
        {
            options.AnalyzerId = "prebuilt-documentSearch";
            options.MaxWait = TimeSpan.FromMinutes(2);
            options.FileSearchConfig = FileSearchConfig.FromFoundry(
                aiProjectClient,
                vectorStoreId,
                fileSearchTool);
        });

    AIAgent agent = aiProjectClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = "LargeDocAgent",
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a document analyst. Use the file_search tool to find "
                + "relevant sections from the document and answer precisely. Cite specific "
                + "sections when answering.",
        },
        AIContextProviders = [cu],
    });

    AgentSession session = await agent.CreateSessionAsync();

    // Turn 1: Upload — CU extracts and uploads to the vector store automatically.
    Console.WriteLine("\n--- Turn 1: Upload document ---");
    byte[] pdfBytes = await File.ReadAllBytesAsync(pdfPath);
    DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

    AgentResponse r1 = await agent.RunAsync(
        new ChatMessage(
            ChatRole.User,
            [
                new TextContent("What are the key points in this document?"),
                pdf,
            ]),
        session);
    Console.WriteLine($"Agent: {r1}\n");

    // Turn 2: Follow-up — file_search retrieves relevant chunks (token-efficient).
    Console.WriteLine("--- Turn 2: Follow-up (RAG) ---");
    AgentResponse r2 = await agent.RunAsync(
        "What numbers or financial metrics are mentioned?",
        session);
    Console.WriteLine($"Agent: {r2}\n");
}
finally
{
    // 4. Cleanup the vector store. The CU provider's DisposeAsync (triggered by
    //    `await using` above) deletes the uploaded files; we explicitly delete
    //    the vector store here since it was created by this sample.
    Console.WriteLine("--- Cleanup: deleting vector store ---");
    await vectorStoresClient.DeleteVectorStoreAsync(vectorStoreId);
    Console.WriteLine("Done.");
}
