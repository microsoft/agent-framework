// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use TextSearchProvider to add retrieval augmented generation (RAG) capabilities to an AI agent.
// The sample uses an In-Memory vector store, which can easily be replaced with any other vector store that implements the Microsoft.Extensions.VectorData abstractions.
// The TextSearchProvider runs a search against the vector store via the TextSearchStore before each model invocation and injects the results into the model context.
// The TextSearchStore is a sample store implementation that hardcodes a storage schema and uses the vector store to store and retrieve documents.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Data;
using Microsoft.Agents.AI.Samples;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";

AzureOpenAIClient azureOpenAIClient = new(
    new Uri(endpoint),
    new AzureCliCredential());

// Create an In-Memory vector store that uses the Azure OpenAI embedding model to generate embeddings.
VectorStore vectorStore = new InMemoryVectorStore(new()
{
    EmbeddingGenerator = azureOpenAIClient.GetEmbeddingClient(embeddingDeploymentName).AsIEmbeddingGenerator()
});

// Create a store that defines a storage schema, and uses the vector store to store and retrieve documents.
TextSearchStore textSearchStore = new(vectorStore, "product-and-policy-info", 3072);

// Upload sample documents into the store.
await textSearchStore.UpsertDocumentsAsync(GetSampleDocuments());

// Create an adapter function that the TextSearchProvider can use to run searches against the TextSearchStore.
Func<string, CancellationToken, Task<IEnumerable<TextSearchProvider.TextSearchResult>>> SearchAdapter = async (text, ct) =>
{
    // Here we are limiting the search results to the single top result to demonstrate that we are accurately matching
    // specific search results for each question, but in a real world case, more results should be used.
    var searchResults = await textSearchStore.SearchAsync(text, 1, ct);
    return searchResults.Select(r => new TextSearchProvider.TextSearchResult
    {
        SourceName = r.SourceName,
        SourceLink = r.SourceLink,
        Text = r.Text ?? string.Empty,
        RawRepresentation = r
    });
};

// Configure the options for the TextSearchProvider.
TextSearchProviderOptions textSearchOptions = new()
{
    // Run the search prior to every model invocation.
    SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
};

// Create the AI agent with the TextSearchProvider as the AI context provider.
AIAgent agent = azureOpenAIClient
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions
    {
        Instructions = "You are a helpful support specialist for Contoso Outdoors. Answer questions using the provided context and cite the source document when available.",
        AIContextProviderFactory = ctx => new TextSearchProvider(SearchAdapter, ctx.SerializedState, ctx.JsonSerializerOptions, textSearchOptions)
    });

AgentThread thread = agent.GetNewThread();

Console.WriteLine(">> Asking about returns\n");
Console.WriteLine(await agent.RunAsync("Hi! I need help understanding the return policy.", thread));

Console.WriteLine("\n>> Asking about shipping\n");
Console.WriteLine(await agent.RunAsync("How long does standard shipping usually take?", thread));

Console.WriteLine("\n>> Asking about product care\n");
Console.WriteLine(await agent.RunAsync("What is the best way to maintain the TrailRunner tent fabric?", thread));

// Produces some sample search documents.
// Each one contains a source name and link, which the agent can use to cite sources in its responses.
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
