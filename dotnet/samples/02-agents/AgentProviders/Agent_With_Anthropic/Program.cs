// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with Anthropic as the backend.

using Anthropic;
using Anthropic.Foundry;
using Azure.Identity;
using Microsoft.Agents.AI;

string deploymentName = Environment.GetEnvironmentVariable("ANTHROPIC_CHAT_MODEL_NAME") ?? "claude-haiku-4-5";

// The resource is the subdomain name / first name coming before '.services.ai.azure.com' in the endpoint Uri
// ie: https://(resource name).services.ai.azure.com/anthropic/v1/chat/completions
string? resource = Environment.GetEnvironmentVariable("ANTHROPIC_RESOURCE");
string? apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
using AnthropicClient client = (resource is null)
    ? new AnthropicClient() { ApiKey = apiKey ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is required when no ANTHROPIC_RESOURCE is provided") }  // If no resource is provided, use Anthropic public API
    : (apiKey is not null)
        ? new AnthropicFoundryClient(new AnthropicFoundryApiKeyCredentials(apiKey, resource)) // If an apiKey is provided, use Foundry with ApiKey authentication
        : new AnthropicFoundryClient(new AnthropicFoundryIdentityTokenCredentials(new DefaultAzureCredential(), resource, ["https://ai.azure.com/.default"])); // Otherwise, use Foundry with Azure TokenCredential authentication

AIAgent agent = client.AsAIAgent(model: deploymentName, instructions: JokerInstructions, name: JokerName);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
