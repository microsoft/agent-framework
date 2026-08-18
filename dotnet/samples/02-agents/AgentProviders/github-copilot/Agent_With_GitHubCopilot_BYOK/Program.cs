// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure a GitHub Copilot agent with BYOK (Bring Your Own Key),
// routing requests through your own endpoint (OpenAI, Azure OpenAI, Anthropic, or an
// OpenAI-compatible service such as vLLM/LiteLLM/Ollama) instead of the GitHub Copilot backend.
//
// SECURITY NOTE: BYOK uses static credentials (no automatic token refresh) and usage is tracked
// by your provider rather than GitHub. Keep API keys out of source control; load them from
// environment variables or a secret store, as shown here.

using GitHub.Copilot;
using Microsoft.Agents.AI;

string providerType = Environment.GetEnvironmentVariable("BYOK_PROVIDER_TYPE") ?? "openai";
string baseUrl = Environment.GetEnvironmentVariable("BYOK_BASE_URL")
    ?? throw new InvalidOperationException("The BYOK_BASE_URL environment variable is not set.");
string apiKey = Environment.GetEnvironmentVariable("BYOK_API_KEY")
    ?? throw new InvalidOperationException("The BYOK_API_KEY environment variable is not set.");
string modelId = Environment.GetEnvironmentVariable("BYOK_MODEL_ID") ?? "gpt-4o";

// Create and start a Copilot client
await using CopilotClient copilotClient = new();
await copilotClient.StartAsync();

// Provider routes the session through a custom endpoint instead of the GitHub Copilot backend.
// Type is "openai", "azure", or "anthropic". WireApi "completions" is the broadly compatible
// choice; use "responses" for providers that support the OpenAI Responses API. BYOK also
// requires Model to be set at the session level.
SessionConfig sessionConfig = new()
{
    Model = modelId,
    Provider = new ProviderConfig
    {
        Type = providerType,
        WireApi = "completions",
        BaseUrl = baseUrl,
        ApiKey = apiKey,
        ModelId = modelId,
    },
};

AIAgent agent = copilotClient.AsAIAgent(sessionConfig, ownsClient: true);

string prompt = "What are the benefits of using your own API keys with an agent framework?";
Console.WriteLine($"User: {prompt}\n");

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(prompt))
{
    Console.Write(update);
}

Console.WriteLine();
