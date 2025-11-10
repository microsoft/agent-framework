// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Qdrant with a custom schema to add retrieval augmented generation (RAG) capabilities to an AI agent.
// While the sample is using Qdrant, it can easily be replaced with any other vector store that implements the Microsoft.Extensions.VectorData abstractions.
// The TextSearchProvider runs a search against the vector store before each model invocation and injects the results into the model context.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Data;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.Qdrant;
using OpenAI;
using Qdrant.Client;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";
var afOverviewUrl = "https://github.com/MicrosoftDocs/semantic-kernel-docs/blob/main/agent-framework/overview/agent-framework-overview.md";
var afMigrationUrl = "https://raw.githubusercontent.com/MicrosoftDocs/semantic-kernel-docs/refs/heads/main/agent-framework/migration-guide/from-semantic-kernel/index.md";

AzureOpenAIClient azureOpenAIClient = new(
    new Uri(endpoint),
    new AzureCliCredential());

// Create a Qdrant vector store that uses the Azure OpenAI embedding model to generate embeddings.
QdrantClient client = new("localhost");
VectorStore vectorStore = new QdrantVectorStore(client, ownsClient: true, new()
{
    EmbeddingGenerator = azureOpenAIClient.GetEmbeddingClient(embeddingDeploymentName).AsIEmbeddingGenerator()
});

// Create a collection and upsert some text into it.
var documentationCollection = vectorStore.GetCollection<Guid, DocumentationChunk>("documentation");
await documentationCollection.EnsureCollectionDeletedAsync(); // Clear out any data from previous runs.
await documentationCollection.EnsureCollectionExistsAsync();
await UploadDataFromMarkdown(afOverviewUrl, "Microsoft Agent Framework Overview", documentationCollection, 2000, 200);
await UploadDataFromMarkdown(afMigrationUrl, "Semantic Kernel to Microsoft Agent Framework Migration Guide", documentationCollection, 2000, 200);

// Create an adapter function that the TextSearchProvider can use to run searches against the collection.
Func<string, CancellationToken, Task<IEnumerable<TextSearchProvider.TextSearchResult>>> SearchAdapter = async (text, ct) =>
{
    List<TextSearchProvider.TextSearchResult> results = [];
    await foreach (var result in documentationCollection.SearchAsync(text, 5, cancellationToken: ct))
    {
        results.Add(new TextSearchProvider.TextSearchResult
        {
            SourceName = result.Record.SourceName,
            SourceLink = result.Record.SourceLink,
            Text = result.Record.Text ?? string.Empty,
            RawRepresentation = result
        });
    }
    return results;
};

// Configure the options for the TextSearchProvider.
TextSearchProviderOptions textSearchOptions = new()
{
    // Run the search prior to every model invocation.
    SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
    // Use up to 4 recent messages when searching so that searches
    // still produce valuable results even when the user is referring
    // back to previous messages in their request.
    RecentMessageMemoryLimit = 5
};

// Create the AI agent with the TextSearchProvider as the AI context provider.
AIAgent agent = azureOpenAIClient
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions
    {
        Instructions = "You are a helpful support specialist for the Microsoft Agent Framework. Answer questions using the provided context and cite the source document when available. Keep responses brief.",
        AIContextProviderFactory = ctx => new TextSearchProvider(SearchAdapter, ctx.SerializedState, ctx.JsonSerializerOptions, textSearchOptions)
    });

AgentThread thread = agent.GetNewThread();

Console.WriteLine(">> Asking about SK threads\n");
Console.WriteLine(await agent.RunAsync("Hi! How do I create a thread in Semantic Kernel?", thread));

// Here we are asking a very vague question when taken out of context,
// but since we are including previous messages in our search using RecentMessageMemoryLimit
// the RAG search should still produce useful results.
Console.WriteLine("\n>> Asking about AF threads\n");
Console.WriteLine(await agent.RunAsync("and in Agent Framework?", thread));

Console.WriteLine("\n>> Contrasting Approaches\n");
Console.WriteLine(await agent.RunAsync("Please contrast the two approaches", thread));

Console.WriteLine("\n>> Asking about ancestry\n");
Console.WriteLine(await agent.RunAsync("What are the predecessors to the Agent Framework?", thread));

static async Task UploadDataFromMarkdown(string markdownUrl, string sourceName, VectorStoreCollection<Guid, DocumentationChunk> vectorStoreCollection, int chunkSize, int overlap)
{
    // Download the markdown from the given url.
    using HttpClient client = new();
    var markdown = await client.GetStringAsync(new Uri(markdownUrl));

    // Chunk it into separate parts with some overlap between chunks
    var chunks = new List<DocumentationChunk>();
    for (int i = 0; i < markdown.Length; i += chunkSize)
    {
        var chunk = new DocumentationChunk
        {
            Key = Guid.NewGuid(),
            SourceLink = markdownUrl,
            SourceName = sourceName,
            Text = markdown.Substring(i, Math.Min(chunkSize + overlap, markdown.Length - i))
        };
        chunks.Add(chunk);
    }

    // Upsert each chunk into the provided vector store.
    await vectorStoreCollection.UpsertAsync(chunks);
}

// Data model that defines the database schema we want to use.
internal sealed class DocumentationChunk
{
    [VectorStoreKey]
    public Guid Key { get; set; }
    [VectorStoreData]
    public string SourceLink { get; set; } = string.Empty;
    [VectorStoreData]
    public string SourceName { get; set; } = string.Empty;
    [VectorStoreData]
    public string Text { get; set; } = string.Empty;
    [VectorStoreVector(Dimensions: 3072)]
    public string Embedding => this.Text;
}
