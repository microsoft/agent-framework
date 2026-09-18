// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add Retrieval Augmented Generation (RAG) capabilities to a hosted
// agent using Azure AI Search. The sample assumes the search index has already been provisioned
// and populated out of band (see README.md for the required schema and example seed content).
// A SearchClient-backed adapter is plugged into TextSearchProvider, which runs a keyword search
// against the index before each model invocation and injects the matching documents into the
// model context.

using Azure;
using Azure.AI.Projects;
using Azure.Identity;
using Azure.Search.Documents;
using Azure.Search.Documents.Models;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string projectEndpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o")!;

string searchEndpoint = FirstNonBlank(System.Environment.GetEnvironmentVariable("AZURE_SEARCH_ENDPOINT"))
    ?? throw new InvalidOperationException("AZURE_SEARCH_ENDPOINT is not set.");
string searchIndexName = FirstNonBlank(System.Environment.GetEnvironmentVariable("AZURE_SEARCH_INDEX_NAME"))
    ?? throw new InvalidOperationException("AZURE_SEARCH_INDEX_NAME is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential. Try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in
// production). The dev credential is scope aware so a single instance serves both Foundry and
// Azure AI Search clients (each Azure SDK client requests a token for its own audience).
var credential = new DefaultAzureCredential();

// Connect to the pre-provisioned search index. The caller is expected to have created the
// index and populated it with documents matching the schema (id / content / sourceName /
// sourceLink) before running this sample. See README.md for an example provisioning script.
var searchClient = new SearchClient(new Uri(searchEndpoint), searchIndexName, credential);

TextSearchProviderOptions textSearchOptions = new()
{
    SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
    RecentMessageMemoryLimit = 6,
};

AIAgent agent = new AIProjectClient(new Uri(projectEndpoint), credential)
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-azure-search-rag",
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful support specialist for Contoso Outdoors. " +
                           "Answer questions using the provided context and cite the source document when available.",
        },
        AIContextProviders = [new TextSearchProvider(CreateSearchAdapter(searchClient), textSearchOptions)]
    });

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();


app.Run();

static string? FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate));

// ── Search adapter ───────────────────────────────────────────────────────────
// Wraps a SearchClient as the delegate TextSearchProvider expects. Keyword/full-text only;
// no embeddings. Returns the top results and projects them into TextSearchResult entries
// the provider will inject into the model context.

static Func<string, CancellationToken, Task<IEnumerable<TextSearchProvider.TextSearchResult>>>
    CreateSearchAdapter(SearchClient client, int top = 3) =>
    async (query, cancellationToken) =>
    {
        var options = new SearchOptions { Size = top };
        Response<SearchResults<SearchDocument>> response =
            await client.SearchAsync<SearchDocument>(query, options, cancellationToken).ConfigureAwait(false);

        var results = new List<TextSearchProvider.TextSearchResult>();
        await foreach (SearchResult<SearchDocument> hit in response.Value.GetResultsAsync().WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            results.Add(new TextSearchProvider.TextSearchResult
            {
                SourceName = hit.Document.TryGetValue("sourceName", out var name) ? name?.ToString() ?? string.Empty : string.Empty,
                SourceLink = hit.Document.TryGetValue("sourceLink", out var link) ? link?.ToString() ?? string.Empty : string.Empty,
                Text = hit.Document.TryGetValue("content", out var content) ? content?.ToString() ?? string.Empty : string.Empty,
                RawRepresentation = hit
            });
        }

        return results;
    };
