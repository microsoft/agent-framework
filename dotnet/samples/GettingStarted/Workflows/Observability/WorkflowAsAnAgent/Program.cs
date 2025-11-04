// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace WorkflowAsAnAgentObservabilitySample;

/// <summary>
/// This sample shows how to enable OpenTelemetry observability for workflows when
/// using them as <see cref="AIAgent"/>s.
///
/// In this example, we create a workflow that uses two language agents to process
/// input concurrently, one that responds in French and another that responds in English.
///
/// You will interact with the workflow in an interactive loop, sending messages and receiving
/// streaming responses from the workflow as if it were an agent who responds in both languages.
///
/// OpenTelemetry observability is enabled at multiple levels:
/// 1. At the chat client level, capturing telemetry for interactions with the Azure OpenAI service.
/// 2. At the agent level, capturing telemetry for agent operations.
/// 3. At the workflow level, capturing telemetry for workflow execution.
///
/// Traces will be sent to an Aspire dashboard via an OTLP endpoint, and optionally to
/// Azure Monitor if an Application Insights connection string is provided.
///
/// Learn how to set up an Aspire dashboard here:
/// https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone?tabs=bash
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - This sample uses concurrent processing.
/// - An Azure OpenAI endpoint and deployment name.
/// - An Application Insights resource for telemetry (optional).
/// </remarks>
public static class Program
{
    private const string SourceName = "Workflow.ApplicationInsightsSample";
    private static readonly ActivitySource s_activitySource = new(SourceName);

    private static async Task Main()
    {
        // Set up observability
        var applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");
        var otlpEndpoint = Environment.GetEnvironmentVariable("OTLP_ENDPOINT") ?? "http://localhost:4317";

        var resourceBuilder = ResourceBuilder
            .CreateDefault()
            .AddService("WorkflowSample");

        var traceProviderBuilder = Sdk.CreateTracerProviderBuilder()
            .SetResourceBuilder(resourceBuilder)
            .AddSource("Microsoft.Agents.AI.*") // Agent Framework telemetry
            .AddSource("Microsoft.Extensions.AI.*") // Extensions AI telemetry
            .AddSource(SourceName);

        traceProviderBuilder.AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint));
        if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
        {
            traceProviderBuilder.AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString);
        }

        using var traceProvider = traceProviderBuilder.Build();

        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
            .GetChatClient(deploymentName)
            .AsIChatClient()
            .AsBuilder()
            .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true) // enable telemetry at the chat client level
            .Build();

        // Start a root activity for the application
        using var activity = s_activitySource.StartActivity("main");
        Console.WriteLine($"Operation/Trace ID: {Activity.Current?.TraceId}");

        // Create the workflow and turn it into an agent with OpenTelemetry instrumentation
        var workflow = WorkflowHelper.GetWorkflow(chatClient, SourceName);
        var agent = new OpenTelemetryAgent(workflow.AsAgent("workflow-agent", "Workflow Agent"), SourceName)
        {
            EnableSensitiveData = true  // enable sensitive data at the agent level such as prompts and responses
        };
        var thread = agent.GetNewThread();

        // Start an interactive loop to interact with the workflow as if it were an agent
        while (true)
        {
            Console.WriteLine();
            Console.Write("User (or 'exit' to quit): ");
            string? input = Console.ReadLine();
            if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
            {
                break;
            }

            await ProcessInputAsync(agent, thread, input);
        }

        // Helper method to process user input and display streaming responses. To display
        // multiple interleaved responses correctly, we buffer updates by message ID and
        // re-render all messages on each update.
        static async Task ProcessInputAsync(AIAgent agent, AgentThread thread, string input)
        {
            Dictionary<string, List<AgentRunResponseUpdate>> buffer = [];
            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(input, thread))
            {
                if (update.MessageId is null || string.IsNullOrEmpty(update.Text))
                {
                    // skip updates that don't have a message ID or text
                    continue;
                }
                Console.Clear();

                if (!buffer.TryGetValue(update.MessageId, out List<AgentRunResponseUpdate>? value))
                {
                    value = [];
                    buffer[update.MessageId] = value;
                }
                value.Add(update);

                foreach (var (messageId, segments) in buffer)
                {
                    string combinedText = string.Concat(segments);
                    Console.WriteLine($"{segments[0].AuthorName}: {combinedText}");
                    Console.WriteLine();
                }
            }
        }
    }
}
