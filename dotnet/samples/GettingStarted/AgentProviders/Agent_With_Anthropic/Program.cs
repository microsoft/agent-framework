// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with Anthropic as the backend.

using System.Net.Http.Headers;
using Anthropic;
using Anthropic.Foundry;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Sample;

var deploymentName = Environment.GetEnvironmentVariable("ANTHROPIC_DEPLOYMENT_NAME") ?? "claude-haiku-4-5";

// The resource is the subdomain name / first name coming before '.services.ai.azure.com' in the endpoint Uri
// ie: https://(resource name).services.ai.azure.com/anthropic/v1/chat/completions
string? resource = Environment.GetEnvironmentVariable("ANTHROPIC_RESOURCE");
string? apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

AnthropicClient? client = (resource is null)
    ? new AnthropicClient() { APIKey = apiKey ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is required when no ANTHROPIC_RESOURCE is provided") }  // If no resource is provided, use Anthropic public API
    : (apiKey is not null)
        ? new AnthropicFoundryClient(new AnthropicFoundryApiKeyCredentials(apiKey, resource)) // If an apiKey is provided, use Foundry with ApiKey authentication
        : new AnthropicFoundryClient(new AnthropicAzureTokenCredential(new AzureCliCredential(), resource)); // Otherwise, use Foundry with Azure Client authentication

AIAgent agent = client.AsAIAgent(model: deploymentName, instructions: JokerInstructions, name: JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

namespace Sample
{
    /// <summary>
    /// Provides methods for invoking the Azure hosted Anthropic models using <see cref="TokenCredential"/> types.
    /// </summary>
    public sealed class AnthropicAzureTokenCredential(TokenCredential tokenCredential, string resourceName) : IAnthropicFoundryCredentials
    {
        /// <inheritdoc/>
        public string ResourceName { get; } = resourceName;

        /// <inheritdoc/>
        public void Apply(HttpRequestMessage requestMessage)
        {
            requestMessage.Headers.Authorization = new AuthenticationHeaderValue(
                    scheme: "bearer",
                    parameter: tokenCredential.GetToken(new TokenRequestContext(scopes: ["https://ai.azure.com/.default"]), CancellationToken.None)
                        .Token);
        }
    }
}
