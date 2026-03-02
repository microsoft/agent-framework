// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend that logs telemetry using OpenTelemetry.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenTelemetry;
using OpenTelemetry.Trace;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");

// Create TracerProvider with console exporter
// This will output the telemetry data to the console.
string sourceName = Guid.NewGuid().ToString("N");
var tracerProviderBuilder = Sdk.CreateTracerProviderBuilder()
    .AddSource(sourceName)
    .AddConsoleExporter();
if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    tracerProviderBuilder.AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString);
}
using var tracerProvider = tracerProviderBuilder.Build();

// Create the agent, and enable OpenTelemetry instrumentation.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "Joker",
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are good at telling jokes." },
    })
    .AsBuilder()
    .UseOpenTelemetry(sourceName: sourceName)
    .Build();

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
