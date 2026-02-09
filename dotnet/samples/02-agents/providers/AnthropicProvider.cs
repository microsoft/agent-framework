// Copyright (c) Microsoft. All rights reserved.

// Provider: Anthropic
// Create an agent using Anthropic (Claude) as the backend.
// Supports direct Anthropic API or Azure AI Foundry-hosted Anthropic models.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using Anthropic;
using Anthropic.Foundry;
using Azure.Identity;
using Microsoft.Agents.AI;

string deploymentName = Environment.GetEnvironmentVariable("ANTHROPIC_DEPLOYMENT_NAME") ?? "claude-haiku-4-5";

// The resource is the subdomain in the Azure AI endpoint URI
string? resource = Environment.GetEnvironmentVariable("ANTHROPIC_RESOURCE");
string? apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");

// <anthropic>
using AnthropicClient client = (resource is null)
    ? new AnthropicClient() { ApiKey = apiKey ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is required when no ANTHROPIC_RESOURCE is provided") }
    : (apiKey is not null)
        ? new AnthropicFoundryClient(new AnthropicFoundryApiKeyCredentials(apiKey, resource))
        : new AnthropicFoundryClient(new AnthropicFoundryIdentityTokenCredentials(new AzureCliCredential(), resource, ["https://ai.azure.com/.default"]));

AIAgent agent = client.AsAIAgent(model: deploymentName, instructions: "You are good at telling jokes.", name: "JokerAgent");
// </anthropic>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
