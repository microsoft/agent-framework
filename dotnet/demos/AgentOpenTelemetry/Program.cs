// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.Metrics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

const string SourceName = "OpenTelemetryAspire.ConsoleApp";
const string ServiceName = "AgentOpenTelemetry";

// Enable telemetry for agents
AppContext.SetSwitch("Microsoft.Extensions.AI.Agents.EnableTelemetry", true);

// Configure OpenTelemetry for Aspire dashboard
var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4318";

// Create a resource to identify this service (like Python example)
var resource = ResourceBuilder.CreateDefault()
    .AddService(ServiceName, serviceVersion: "1.0.0")
    .AddAttributes(new Dictionary<string, object>
    {
        ["service.instance.id"] = Environment.MachineName,
        ["deployment.environment"] = "development"
    })
    .Build();

// Setup tracing with resource
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddSource(SourceName) // Our custom activity source
    .AddSource("Microsoft.Extensions.AI.Agents") // Agent Framework telemetry
    .AddHttpClientInstrumentation() // Capture HTTP calls to OpenAI
    .AddOtlpExporter(options =>
    {
        options.Endpoint = new Uri(otlpEndpoint);
    })
    .Build();

// Setup metrics with resource and instrument name filtering (like Python example)
using var meterProvider = Sdk.CreateMeterProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddMeter(SourceName) // Our custom meter
    .AddMeter("Microsoft.Extensions.AI.Agents") // Agent Framework metrics
    .AddHttpClientInstrumentation() // HTTP client metrics
    .AddRuntimeInstrumentation() // .NET runtime metrics
    .AddOtlpExporter(options =>
    {
        options.Endpoint = new Uri(otlpEndpoint);
    })
    .Build();

using var activitySource = new ActivitySource(SourceName);
using var meter = new Meter(SourceName);

// Create custom metrics (similar to Python example)
var interactionCounter = meter.CreateCounter<int>("agent_interactions_total", description: "Total number of agent interactions");
var responseTimeHistogram = meter.CreateHistogram<double>("agent_response_time_seconds", description: "Agent response time in seconds");

Console.WriteLine("=== OpenTelemetry Aspire Demo ===\n");
Console.WriteLine("This demo shows OpenTelemetry integration with the Agent Framework.\n");
Console.WriteLine("You can view the telemetry data in the Aspire Dashboard.\n");
Console.WriteLine("Type your message and press Enter. Type 'exit' to quit.\n");

// Create the chat client - try Azure OpenAI first
var configuredEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4317";
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT", EnvironmentVariableTarget.Machine) ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
        .GetChatClient(deploymentName)
        .AsIChatClient();

// Create the agent with OpenTelemetry instrumentation
var baseAgent = new ChatClientAgent(
    chatClient,
    name: "OpenTelemetryDemoAgent",
    instructions: "You are a helpful assistant that provides concise and informative responses.");

using var agent = baseAgent.WithOpenTelemetry(sourceName: SourceName);
var thread = agent.GetNewThread();

// Create a parent span for the entire agent session
using var sessionActivity = activitySource.StartActivity("Agent Session");
sessionActivity?.SetTag("agent.name", "OpenTelemetryDemoAgent");
sessionActivity?.SetTag("session.id", thread.Id ?? Guid.NewGuid().ToString());
sessionActivity?.SetTag("session.start_time", DateTimeOffset.UtcNow.ToString("O"));

var interactionCount = 0;

while (true)
{
    Console.Write("You: ");
    var userInput = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(userInput) || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    interactionCount++;

    // Create a child span for each individual interaction
    using var activity = activitySource.StartActivity("Agent Interaction");
    activity?.SetTag("user.input", userInput);
    activity?.SetTag("agent.name", "OpenTelemetryDemoAgent");
    activity?.SetTag("interaction.number", interactionCount);

    var stopwatch = System.Diagnostics.Stopwatch.StartNew();

    try
    {
        Console.WriteLine("Agent: Processing...");

        // Run the agent (this will create its own internal telemetry spans)
        var response = await agent.RunAsync(userInput, thread);

        Console.WriteLine($"Agent: {response.Messages.LastOrDefault()?.Text}");
        Console.WriteLine();

        stopwatch.Stop();

        // Record metrics (similar to Python example)
        interactionCounter.Add(1, new KeyValuePair<string, object?>("status", "success"));
        responseTimeHistogram.Record(stopwatch.Elapsed.TotalSeconds,
            new KeyValuePair<string, object?>("status", "success"));

        activity?.SetTag("response.success", true);
        activity?.SetTag("response.message_count", response.Messages.Count);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
        Console.WriteLine();

        stopwatch.Stop();

        // Record error metrics
        interactionCounter.Add(1, new KeyValuePair<string, object?>("status", "error"));
        responseTimeHistogram.Record(stopwatch.Elapsed.TotalSeconds,
            new KeyValuePair<string, object?>("status", "error"));

        activity?.SetTag("response.success", false);
        activity?.SetTag("error.message", ex.Message);
        activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
    }
}

// Add session summary to the parent span
sessionActivity?.SetTag("session.total_interactions", interactionCount);
sessionActivity?.SetTag("session.end_time", DateTimeOffset.UtcNow.ToString("O"));

Console.WriteLine("Goodbye!");
