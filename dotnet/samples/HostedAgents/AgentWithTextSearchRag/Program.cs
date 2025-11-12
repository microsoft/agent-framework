// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use TextSearchProvider to add retrieval augmented generation (RAG)
// capabilities to an AI agent. The provider runs a search against an external knowledge base
// before each model invocation and injects the results into the model context.

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Data;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

TextSearchProviderOptions textSearchOptions = new()
{
    // Run the search prior to every model invocation and keep a short rolling window of conversation context.
    SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
    RecentMessageMemoryLimit = 6,
};

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions
    {
        Instructions = "You are a helpful support specialist for Contoso Outdoors. Answer questions using the provided context and cite the source document when available.",
        AIContextProviderFactory = ctx => new TextSearchProvider(MockSearchAsync, ctx.SerializedState, ctx.JsonSerializerOptions, textSearchOptions)
    });

await agent.RunAIAgentAsync();

static Task<IEnumerable<TextSearchProvider.TextSearchResult>> MockSearchAsync(string query, CancellationToken cancellationToken)
{
    // The mock search inspects the user's question and returns pre-defined snippets
    // that resemble documents stored in an external knowledge source.
    List<TextSearchProvider.TextSearchResult> results = new();

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
