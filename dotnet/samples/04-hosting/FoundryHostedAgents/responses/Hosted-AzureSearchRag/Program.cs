// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add Retrieval Augmented Generation (RAG) capabilities to a hosted
// agent using Azure AI Search. The sample assumes the search index has already been provisioned
// and populated out of band (see README.md for the required schema and example seed content).
// A SearchClient-backed adapter is plugged into TextSearchProvider, which runs a keyword search
// against the index before each model invocation and injects the matching documents into the
// model context.

using Azure;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using Azure.Search.Documents;
using Azure.Search.Documents.Models;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string projectEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

string searchEndpoint = Environment.GetEnvironmentVariable("AZURE_SEARCH_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_SEARCH_ENDPOINT is not set.");
string searchIndexName = Environment.GetEnvironmentVariable("AZURE_SEARCH_INDEX_NAME")
    ?? throw new InvalidOperationException("AZURE_SEARCH_INDEX_NAME is not set.");

// Use a chained credential. Try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in
// production). The dev credential is scope aware so a single instance serves both Foundry and
// Azure AI Search clients (each Azure SDK client requests a token for its own audience).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

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
        Name = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-azure-search-rag",
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

if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

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

/// <summary>
/// A scope aware <see cref="TokenCredential"/> for local Docker debugging only.
/// Reads pre-fetched bearer tokens from environment variables, dispensing the right token
/// based on the requested scope:
/// <list type="bullet">
///   <item><description><c>ai.azure.com</c> scopes -> <c>AZURE_BEARER_TOKEN_FOUNDRY</c></description></item>
///   <item><description><c>search.azure.com</c> scopes -> <c>AZURE_BEARER_TOKEN_SEARCH</c></description></item>
/// </list>
/// For any other scope, throws <see cref="CredentialUnavailableException"/> so a chained
/// credential will fall through. This should NOT be used in production: tokens expire (~1 hour)
/// and cannot be refreshed.
///
/// Generate the tokens on your host and pass them to the container:
/// <code>
///   export AZURE_BEARER_TOKEN_FOUNDRY=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   export AZURE_BEARER_TOKEN_SEARCH=$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN_FOUNDRY -e AZURE_BEARER_TOKEN_SEARCH ...
/// </code>
/// </summary>
internal sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string FoundryEnvironmentVariable = "AZURE_BEARER_TOKEN_FOUNDRY";
    private const string SearchEnvironmentVariable = "AZURE_BEARER_TOKEN_SEARCH";

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => Resolve(requestContext.Scopes);

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => new(Resolve(requestContext.Scopes));

    private static AccessToken Resolve(IReadOnlyList<string> scopes)
    {
        string? envVar = null;
        foreach (var scope in scopes)
        {
            if (scope.Contains("search.azure.com", StringComparison.OrdinalIgnoreCase))
            {
                envVar = SearchEnvironmentVariable;
                break;
            }

            if (scope.Contains("ai.azure.com", StringComparison.OrdinalIgnoreCase))
            {
                envVar = FoundryEnvironmentVariable;
                break;
            }
        }

        if (envVar is null)
        {
            throw new CredentialUnavailableException(
                $"DevTemporaryTokenCredential cannot serve scopes [{string.Join(", ", scopes)}]; falling through.");
        }

        var token = Environment.GetEnvironmentVariable(envVar);
        if (string.IsNullOrEmpty(token) || string.Equals(token, "DefaultAzureCredential", StringComparison.Ordinal))
        {
            throw new CredentialUnavailableException(
                $"{envVar} environment variable is not set; falling through to next credential.");
        }

        return new AccessToken(token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
