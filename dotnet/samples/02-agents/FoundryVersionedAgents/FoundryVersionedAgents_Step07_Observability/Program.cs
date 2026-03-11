// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Microsoft Foundry Agents as the backend that logs telemetry using OpenTelemetry.

using Azure.Identity;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenTelemetry;
using OpenTelemetry.Trace;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string? applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Create TracerProvider with console exporter
// This will output the telemetry data to the console.
string sourceName = Guid.NewGuid().ToString("N");
TracerProviderBuilder tracerProviderBuilder = Sdk.CreateTracerProviderBuilder()
    .AddSource(sourceName)
    .AddConsoleExporter();
if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    tracerProviderBuilder.AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString);
}
using var tracerProvider = tracerProviderBuilder.Build();

// Define the agent you want to create. (Prompt Agent in this case)
FoundryVersionedAgent foundryAgent = await FoundryVersionedAgent.CreateAIAgentAsync(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    name: JokerName,
    model: deploymentName,
    instructions: JokerInstructions);
AIAgent agent = foundryAgent
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
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await FoundryVersionedAgent.DeleteAIAgentAsync(foundryAgent);
