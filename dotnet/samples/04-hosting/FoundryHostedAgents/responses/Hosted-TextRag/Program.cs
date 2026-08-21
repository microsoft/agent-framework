// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use TextSearchProvider to add retrieval augmented generation (RAG)
// capabilities to a hosted agent. The provider runs a search against an external knowledge base
// before each model invocation and injects the results into the model context. It is deployed to
// Foundry directly from source (code / ZIP upload), so the platform builds and runs your code with
// no container image.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var endpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-text-rag";

TextSearchProviderOptions textSearchOptions = new()
{
    SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
    RecentMessageMemoryLimit = 6,
};

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = agentName,
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful support specialist for Contoso Outdoors. Answer questions using the provided context and cite the source document when available.",
        },
        AIContextProviders = [new TextSearchProvider(MockSearchAsync, textSearchOptions)]
    });

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;

// ── Mock search function ─────────────────────────────────────────────────────
// In production, replace this with a real search provider (e.g., Azure AI Search).

static Task<IEnumerable<TextSearchProvider.TextSearchResult>> MockSearchAsync(string query, CancellationToken cancellationToken)
{
    List<TextSearchProvider.TextSearchResult> results = [];

    if (query.Contains("return", StringComparison.OrdinalIgnoreCase) || query.Contains("refund", StringComparison.OrdinalIgnoreCase))
    {
        results.Add(new()
        {
            SourceName = "Contoso Outdoors Return Policy",
            SourceLink = "https://contoso.com/policies/returns",
            Text = "Customers may return any item within 30 days of delivery. Items should be unused and include original packaging. Refunds are issued to the original payment method within 5 business days of inspection."
        });
    }

    if (query.Contains("shipping", StringComparison.OrdinalIgnoreCase))
    {
        results.Add(new()
        {
            SourceName = "Contoso Outdoors Shipping Guide",
            SourceLink = "https://contoso.com/help/shipping",
            Text = "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days within the continental United States. Expedited options are available at checkout."
        });
    }

    if (query.Contains("tent", StringComparison.OrdinalIgnoreCase) || query.Contains("fabric", StringComparison.OrdinalIgnoreCase))
    {
        results.Add(new()
        {
            SourceName = "TrailRunner Tent Care Instructions",
            SourceLink = "https://contoso.com/manuals/trailrunner-tent",
            Text = "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow it to air dry completely before storage and avoid prolonged UV exposure to extend the lifespan of the waterproof coating."
        });
    }

    return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);
}
