// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with Anthropic as the backend.

using System.ClientModel;
using System.Net.Http.Headers;
using Anthropic;
using Anthropic.Core;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Sample;

var deploymentName = Environment.GetEnvironmentVariable("ANTHROPIC_DEPLOYMENT_NAME") ?? "claude-haiku-4-5";

// The resource is the subdomain name / first name coming before '.services.ai.azure.com' in the endpoint Uri
// ie: https://(resource name).services.ai.azure.com/anthropic/v1/chat/completions
var resource = Environment.GetEnvironmentVariable("ANTHROPIC_RESOURCE");
var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

AnthropicClient? client = (resource is null)
    ? new AnthropicClient() { APIKey = apiKey ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is required when no ANTHROPIC_RESOURCE is provided") }  // If no resource is provided, use Anthropic public API
    : (apiKey is not null)
        ? new AnthropicFoundryClient(resource, new ApiKeyCredential(apiKey)) // If an apiKey is provided, use Foundry with ApiKey authentication
        : new AnthropicFoundryClient(resource, new AzureCliCredential()); // Otherwise, use Foundry with Azure Client authentication

AIAgent agent = client.CreateAIAgent(model: deploymentName, instructions: JokerInstructions, name: JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

namespace Sample
{
    /// <summary>
    /// Provides methods for invoking the Azure hosted Anthropic api.
    /// </summary>
    public class AnthropicFoundryClient : AnthropicClient
    {
        private readonly TokenCredential _tokenCredential;
        private readonly string _resourceName;

        /// <summary>
        /// Creates a new instance of the <see cref="AnthropicFoundryClient"/>.
        /// </summary>
        /// <param name="resourceName">The service resource subdomain name to use in the anthropic azure endpoint</param>
        /// <param name="tokenCredential">The credential provider. Use any specialization of <see cref="TokenCredential"/> to get your access token in supported environments.</param>
        /// <param name="options">Set of <see cref="Anthropic.Core.ClientOptions"/> client option configurations</param>
        /// <exception cref="ArgumentNullException">Resource is null</exception>
        /// <exception cref="ArgumentNullException">TokenCredential is null</exception>
        /// <remarks>
        /// Any <see cref="Anthropic.Core.ClientOptions"/> APIKey or Bearer token provided will be ignored in favor of the <see cref="TokenCredential"/> provided in the constructor
        /// </remarks>
        public AnthropicFoundryClient(string resourceName, TokenCredential tokenCredential, Anthropic.Core.ClientOptions? options = null) : base(options ?? new())
        {
            this._resourceName = resourceName ?? throw new ArgumentNullException(nameof(resourceName));
            this._tokenCredential = tokenCredential ?? throw new ArgumentNullException(nameof(tokenCredential));
            this.BaseUrl = new Uri($"https://{this._resourceName}.services.ai.azure.com/anthropic", UriKind.Absolute);
        }

        /// <summary>
        /// Creates a new instance of the <see cref="AnthropicFoundryClient"/>.
        /// </summary>
        /// <param name="resourceName">The service resource subdomain name to use in the anthropic azure endpoint</param>
        /// <param name="apiKeyCredential">The api key.</param>
        /// <param name="options">Set of <see cref="Anthropic.Core.ClientOptions"/> client option configurations</param>
        /// <exception cref="ArgumentNullException">Resource is null</exception>
        /// <exception cref="ArgumentNullException">Api key is null</exception>
        /// <remarks>
        /// Any <see cref="Anthropic.Core.ClientOptions"/> APIKey or Bearer token provided will be ignored in favor of the <see cref="ApiKeyCredential"/> provided in the constructor
        /// </remarks>
        public AnthropicFoundryClient(string resourceName, ApiKeyCredential apiKeyCredential, Anthropic.Core.ClientOptions? options = null) :
            this(resourceName, apiKeyCredential is null
                ? throw new ArgumentNullException(nameof(apiKeyCredential))
                : DelegatedTokenCredential.Create((_, _) =>
                {
                    apiKeyCredential.Deconstruct(out string dangerousCredential);
                    return new AccessToken(dangerousCredential, DateTimeOffset.MaxValue);
                }),
                options)
        { }

        public override IAnthropicClient WithOptions(Func<Anthropic.Core.ClientOptions, Anthropic.Core.ClientOptions> modifier)
            => this;

        protected override ValueTask BeforeSend<T>(
            HttpRequest<T> request,
            HttpRequestMessage requestMessage,
            CancellationToken cancellationToken
        )
        {
            var accessToken = this._tokenCredential.GetToken(new TokenRequestContext(scopes: ["https://ai.azure.com/.default"]), cancellationToken);

            requestMessage.Headers.Authorization = new AuthenticationHeaderValue("bearer", accessToken.Token);

            return default;
        }
    }
}
