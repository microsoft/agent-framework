// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to enable OpenTelemetry observability for durable workflows.
// Traces are sent to an Aspire Dashboard via OTLP, and optionally to Azure Monitor
// if an Application Insights connection string is provided.
//
// The workflow is a simple text processing pipeline:
//   UppercaseExecutor -> ReverseTextExecutor
//
// For input "Hello, World!", the workflow produces "!DLROW ,OLLEH".
//
// OpenTelemetry captures traces at the workflow level (executor dispatch, edge routing)
// and at the Durable Task level (orchestration replay, activity execution).
//
// Learn how to set up an Aspire dashboard here:
// https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone?tabs=bash

using System.Diagnostics;
using Azure.Monitor.OpenTelemetry.Exporter;
using DurableWorkflowObservability;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

// ── Configuration ────────────────────────────────────────────────────────────
string sourceName = "DurableWorkflow.ObservabilitySample";
ActivitySource activitySource = new(sourceName);

string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";
string? applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");
string otlpEndpoint = Environment.GetEnvironmentVariable("OTLP_ENDPOINT") ?? "http://localhost:4317";

// ── OpenTelemetry Setup ──────────────────────────────────────────────────────
ResourceBuilder resourceBuilder = ResourceBuilder
    .CreateDefault()
    .AddService("DurableWorkflowObservabilitySample");

TracerProviderBuilder traceProviderBuilder = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(resourceBuilder)
    .AddSource("Microsoft.Agents.AI.Workflows*") // Workflow-level telemetry (executors, edges)
    .AddSource("Microsoft.Agents.AI.DurableTask*") // Durable workflow telemetry (orchestration, dispatch, routing)
    .AddSource(sourceName)                        // Application-level telemetry
    .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint));

// Optionally add Azure Monitor exporter if connection string is provided
if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    traceProviderBuilder.AddAzureMonitorTraceExporter(
        options => options.ConnectionString = applicationInsightsConnectionString);
}

using TracerProvider? traceProvider = traceProviderBuilder.Build();

// Start a root activity so all workflow spans are correlated under one trace
using Activity? rootActivity = activitySource.StartActivity("main");
Console.WriteLine($"Operation/Trace ID: {Activity.Current?.TraceId}");

// ── Define executors and build the workflow ──────────────────────────────────
UppercaseExecutor uppercase = new();
ReverseTextExecutor reverse = new();

Workflow textProcessing = new WorkflowBuilder(uppercase)
    .WithName("TextProcessing")
    .WithDescription("Convert text to uppercase then reverse it")
    .AddEdge(uppercase, reverse)
    .Build();

// ── Configure the host with durable workflow support ─────────────────────────
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            workflowOptions => workflowOptions.AddWorkflow(textProcessing),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

// ── Interactive loop ─────────────────────────────────────────────────────────
Console.WriteLine();
Console.WriteLine("Durable Workflow Observability Sample");
Console.WriteLine("Workflow: UppercaseExecutor -> ReverseTextExecutor");
Console.WriteLine("Traces are exported via OTLP to: " + otlpEndpoint);
if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    Console.WriteLine("Traces are also exported to Azure Monitor (Application Insights).");
}

Console.WriteLine();
Console.WriteLine("Enter text to process (or 'exit' to quit):");

while (true)
{
    Console.Write("> ");
    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        // Create a child activity for each workflow invocation
        using Activity? invocationActivity = activitySource.StartActivity("ProcessText");
        invocationActivity?.SetTag("input.text", input);

        Console.WriteLine($"Starting workflow for input: \"{input}\"...");

        IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await workflowClient.RunAsync(textProcessing, input);
        Console.WriteLine($"Run ID: {run.RunId}");

        Console.WriteLine("Waiting for workflow to complete...");
        string? result = await run.WaitForCompletionAsync<string>();

        invocationActivity?.SetTag("output.text", result);
        Console.WriteLine($"Result: {result}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();
