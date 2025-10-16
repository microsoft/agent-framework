// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI.Workflows;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace WorkflowObservabilitySample;

/// <summary>
/// This sample shows how to enable observability in a workflow and send the traces
/// to be visualized in Application Insights.
///
/// In this example, we create a simple text processing pipeline that:
/// 1. Takes input text and converts it to uppercase using an UppercaseExecutor
/// 2. Takes the uppercase text and reverses it using a ReverseTextExecutor
///
/// The executors are connected sequentially, so data flows from one to the next in order.
/// For input "Hello, World!", the workflow produces "!DLROW ,OLLEH".
/// </summary>
public static class Program
{
    private const string SourceName = "Workflow.ApplicationInsightsSample";
    private static readonly ActivitySource s_activitySource = new(SourceName);

    private static async Task Main()
    {
        var applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING") ?? throw new InvalidOperationException("APPLICATIONINSIGHTS_CONNECTION_STRING is not set.");

        var resourceBuilder = ResourceBuilder
            .CreateDefault()
            .AddService("WorkflowSample");

        using var traceProvider = Sdk.CreateTracerProviderBuilder()
            .SetResourceBuilder(resourceBuilder)
            .AddSource("Microsoft.Agents.AI.Workflows*")
            .AddSource(SourceName)
            .AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString)
            .Build();

        // Start a root activity for the application
        using var activity = s_activitySource.StartActivity("main");
        Console.WriteLine($"Operation/Trace ID: {Activity.Current?.TraceId}");

        // Create the executors
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        // Build the workflow by connecting executors sequentially
        var workflow = new WorkflowBuilder(uppercase)
            .AddEdge(uppercase, reverse)
            .Build();

        // Execute the workflow with input data
        Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}

/// <summary>
/// First executor: converts input text to uppercase.
/// </summary>
internal sealed class UppercaseExecutor() : Executor<string, string>("UppercaseExecutor")
{
    /// <summary>
    /// Processes the input message by converting it to uppercase.
    /// </summary>
    /// <param name="message">The input text to convert</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The input text converted to uppercase</returns>
    public override async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        message.ToUpperInvariant(); // The return value will be sent as a message along an edge to subsequent executors
}

/// <summary>
/// Second executor: reverses the input text and completes the workflow.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    /// <summary>
    /// Processes the input message by reversing the text.
    /// </summary>
    /// <param name="message">The input text to reverse</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The input text reversed</returns>
    public override async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
        => new(message.Reverse().ToArray());
}
