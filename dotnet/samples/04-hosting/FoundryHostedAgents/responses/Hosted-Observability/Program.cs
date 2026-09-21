// Copyright (c) Microsoft. All rights reserved.

// Hosted Observability Agent - demonstrates that the Foundry hosting pipeline
// emits OpenTelemetry traces, metrics and logs with no extra wiring required.
// Two small tools are included so a request produces a span tree covering
// agent invocation, the chat call, and tool execution. It is deployed to Foundry
// directly from source (code / ZIP upload), so the platform builds and runs your
// code with no container image.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var endpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-observability";

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

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: deploymentName,
        instructions: "You are a friendly assistant. Keep your answers brief.",
        name: agentName,
        description: "A hosted agent that demonstrates Foundry observability.",
        tools: [
            AIFunctionFactory.Create(GetCurrentLocation),
            AIFunctionFactory.Create(GetWeather),
        ]);

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;
