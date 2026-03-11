// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add OpenTelemetry observability to an agent.

using Azure.Identity;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenTelemetry;
using OpenTelemetry.Trace;

string? applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");
string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create TracerProvider with console exporter.
string sourceName = Guid.NewGuid().ToString("N");
TracerProviderBuilder tracerProviderBuilder = Sdk.CreateTracerProviderBuilder()
    .AddSource(sourceName)
    .AddConsoleExporter();
if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    tracerProviderBuilder.AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString);
}
using var tracerProvider = tracerProviderBuilder.Build();

AIAgent agent = new FoundryAgent(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent")
    .AsBuilder()
    .UseOpenTelemetry(sourceName: sourceName)
    .Build();

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Invoke the agent with streaming support.
session = await agent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.Write(update);
}

Console.WriteLine();
