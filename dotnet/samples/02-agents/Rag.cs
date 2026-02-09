// Copyright (c) Microsoft. All rights reserved.

// Retrieval Augmented Generation (RAG)
// Add RAG capabilities using TextSearchProvider with a vector store.
// The provider searches relevant documents before each model invocation.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/rag

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Samples;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";

AzureOpenAIClient azureOpenAIClient = new(new Uri(endpoint), new AzureCliCredential());

// <setup_rag>
VectorStore vectorStore = new InMemoryVectorStore(new()
{
    EmbeddingGenerator = azureOpenAIClient.GetEmbeddingClient(embeddingDeploymentName).AsIEmbeddingGenerator()
});

TextSearchStore textSearchStore = new(vectorStore, "product-and-policy-info", 3072);
await textSearchStore.UpsertDocumentsAsync(GetSampleDocuments());

Func<string, CancellationToken, Task<IEnumerable<TextSearchProvider.TextSearchResult>>> SearchAdapter = async (text, ct) =>
{
    var searchResults = await textSearchStore.SearchAsync(text, 1, ct);
    return searchResults.Select(r => new TextSearchProvider.TextSearchResult
    {
        SourceName = r.SourceName,
        SourceLink = r.SourceLink,
        Text = r.Text ?? string.Empty,
        RawRepresentation = r
    });
};

AIAgent agent = azureOpenAIClient
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are a helpful support specialist for Contoso Outdoors. Answer questions using the provided context and cite the source document when available." },
        AIContextProviderFactory = (ctx, ct) => new ValueTask<AIContextProvider>(new TextSearchProvider(SearchAdapter, ctx.SerializedState, ctx.JsonSerializerOptions)),
        ChatHistoryProviderFactory = (ctx, ct) => new ValueTask<ChatHistoryProvider>(new InMemoryChatHistoryProvider(ctx.SerializedState, ctx.JsonSerializerOptions)
            .WithAIContextProviderMessageRemoval()),
    });
// </setup_rag>

// <use_rag>
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine(await agent.RunAsync("Hi! I need help understanding the return policy.", session));
Console.WriteLine(await agent.RunAsync("How long does standard shipping usually take?", session));
Console.WriteLine(await agent.RunAsync("What is the best way to maintain the TrailRunner tent fabric?", session));
// </use_rag>

static IEnumerable<TextSearchDocument> GetSampleDocuments()
{
    yield return new TextSearchDocument
    {
        SourceId = "return-policy-001",
        SourceName = "Contoso Outdoors Return Policy",
        SourceLink = "https://contoso.com/policies/returns",
        Text = "Customers may return any item within 30 days of delivery. Items should be unused and include original packaging. Refunds are issued to the original payment method within 5 business days of inspection."
    };
    yield return new TextSearchDocument
    {
        SourceId = "shipping-guide-001",
        SourceName = "Contoso Outdoors Shipping Guide",
        SourceLink = "https://contoso.com/help/shipping",
        Text = "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days within the continental United States. Expedited options are available at checkout."
    };
    yield return new TextSearchDocument
    {
        SourceId = "tent-care-001",
        SourceName = "TrailRunner Tent Care Instructions",
        SourceLink = "https://contoso.com/manuals/trailrunner-tent",
        Text = "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow it to air dry completely before storage and avoid prolonged UV exposure to extend the lifespan of the waterproof coating."
    };
}
