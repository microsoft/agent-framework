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
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

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

var app = builder.Build();
app.MapFoundryResponses();

if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

/// <summary>
/// A <see cref="TokenCredential"/> for local Docker debugging only.
/// Reads a pre-fetched bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable
/// once at startup. This should NOT be used in production.
///
/// Generate a token on your host and pass it to the container:
///   export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN ...
/// </summary>
internal sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string EnvironmentVariable = "AZURE_BEARER_TOKEN";
    private readonly string? _token;

    public DevTemporaryTokenCredential()
    {
        this._token = Environment.GetEnvironmentVariable(EnvironmentVariable);
    }

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => this.GetAccessToken();

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => new(this.GetAccessToken());

    private AccessToken GetAccessToken()
    {
        if (string.IsNullOrEmpty(this._token) || this._token == "DefaultAzureCredential")
        {
            throw new CredentialUnavailableException($"{EnvironmentVariable} environment variable is not set.");
        }

        return new AccessToken(this._token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
