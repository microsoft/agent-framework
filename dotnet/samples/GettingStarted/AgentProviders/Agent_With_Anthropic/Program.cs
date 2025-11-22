// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1050 // Declare types in namespaces

// This sample shows how to create and use an AI agent with Anthropic as the backend.

using Anthropic;
using Anthropic.Foundry;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;

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
        ? new AnthropicFoundryClient(new AnthropicFoundryApiKeyCredentials(apiKey, resource)) // If an apiKey are provided, use Foundry with ApiKey authentication
        : new AnthropicFoundryClient(new AzureTokenCredential(resource, new AzureCliCredential())); // Otherwise, use Foundry with Azure Client authentication

AIAgent agent = client.CreateAIAgent(model: deploymentName, instructions: JokerInstructions, name: JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

public class AzureTokenCredential : IAnthropicFoundryCredentials
#pragma warning restore CA1050 // Declare types in namespaces
{
    private readonly TokenCredential _tokenCredential;

    public AzureTokenCredential(string resourceName, TokenCredential tokenCredential)
    {
        this.ResourceName = resourceName;
        this._tokenCredential = tokenCredential;
    }

    public string ResourceName { get; }

    public void Apply(HttpRequestMessage requestMessage)
    {
        var accessToken = this._tokenCredential.GetToken(
            new TokenRequestContext(scopes: ["https://ai.azure.com/.default"]),
            cancellationToken: CancellationToken.None);

        requestMessage.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("bearer", accessToken.Token);
    }
}
