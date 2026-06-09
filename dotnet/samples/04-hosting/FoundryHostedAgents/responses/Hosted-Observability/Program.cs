// Copyright (c) Microsoft. All rights reserved.

// Hosted Observability Agent - demonstrates that the Foundry hosting pipeline
// emits OpenTelemetry traces, metrics and logs with no extra wiring required.
// Two small tools are included so a request produces a span tree covering
// agent invocation, the chat call, and tool execution.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// ── Tools ────────────────────────────────────────────────────────────────────

string[] locations = ["New York", "London", "Paris", "Tokyo"];
string[] conditions = ["sunny", "cloudy", "rainy", "stormy"];

[Description("Get the current location of the user.")]
string GetCurrentLocation() => locations[Random.Shared.Next(locations.Length)];

[Description("Get the weather for a given location.")]
string GetWeather(
    [Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is {conditions[Random.Shared.Next(conditions.Length)]} with a high of {Random.Shared.Next(10, 31)}°C.";

// ── Create and host the agent ────────────────────────────────────────────────
//
// AddFoundryResponses automatically wraps `agent` with OpenTelemetryAgent
// (see Microsoft.Agents.AI.Foundry.Hosting.ServiceCollectionExtensions.ApplyOpenTelemetry)
// and the OTLP exporter is registered by Azure.AI.AgentServer.Core's
// AddAgentHostTelemetry(). No additional observability wiring is required.

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
    .AsAIAgent(
        model: deploymentName,
        instructions: "You are a friendly assistant. Keep your answers brief.",
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-observability",
        description: "A hosted agent that demonstrates Foundry observability.",
        tools: [
            AIFunctionFactory.Create(GetCurrentLocation),
            AIFunctionFactory.Create(GetWeather),
        ]);

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
