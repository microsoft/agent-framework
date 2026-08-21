// Copyright (c) Microsoft. All rights reserved.

// Sample: a minimal general-purpose AI assistant hosted as a Foundry Hosted Agent
// using the Responses protocol. It is deployed to Foundry directly from source
// (code / ZIP upload), so the platform builds and runs it with no container image.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var model = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-chat-client-agent";

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
AIAgent agent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(
        model: model,
        instructions: """
            You are a helpful AI assistant hosted as a Foundry Hosted Agent.
            You can help with a wide range of tasks including answering questions,
            providing explanations, brainstorming ideas, and offering guidance.
            Be concise, clear, and helpful in your responses.
            """,
        name: agentName,
        description: "A simple general-purpose AI assistant");

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;
