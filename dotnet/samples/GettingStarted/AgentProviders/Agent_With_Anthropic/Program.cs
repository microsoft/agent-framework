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

AIAgent agent = client.CreateAIAgent(model: deploymentName, instructions: JokerInstructions, name: JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

namespace Sample
{
    /// <summary>
    /// Provides methods for invoking the Azure hosted Anthropic models using <see cref="TokenCredential"/> types.
    /// </summary>
    public sealed class AnthropicAzureTokenCredential : IAnthropicFoundryCredentials
    {
        private readonly TokenCredential _tokenCredential;
        private readonly Lock _lock = new();
        private AccessToken? _cachedAccessToken;

        /// <inheritdoc/>
        public string ResourceName { get; }

        /// <summary>
        /// Creates a new instance of the <see cref="AnthropicAzureTokenCredential"/>.
        /// </summary>
        /// <param name="tokenCredential">The credential provider. Use any specialization of <see cref="TokenCredential"/> to get your access token in supported environments.</param>
        /// <param name="resourceName">The service resource subdomain name to use in the anthropic azure endpoint</param>
        internal AnthropicAzureTokenCredential(TokenCredential tokenCredential, string resourceName)
        {
            this.ResourceName = resourceName ?? throw new ArgumentNullException(nameof(resourceName));
            this._tokenCredential = tokenCredential ?? throw new ArgumentNullException(nameof(tokenCredential));
        }

        /// <inheritdoc/>
        public void Apply(HttpRequestMessage requestMessage)
        {
            lock (this._lock)
            {
                // Add a 5-minute buffer to avoid using tokens that are about to expire
                if (this._cachedAccessToken is null || this._cachedAccessToken.Value.ExpiresOn <= DateTimeOffset.Now.AddMinutes(5))
                {
                    this._cachedAccessToken = this._tokenCredential.GetToken(new TokenRequestContext(scopes: ["https://ai.azure.com/.default"]), CancellationToken.None);
                }
            }

            requestMessage.Headers.Authorization = new AuthenticationHeaderValue("bearer", this._cachedAccessToken.Value.Token);
        }
    }
}
