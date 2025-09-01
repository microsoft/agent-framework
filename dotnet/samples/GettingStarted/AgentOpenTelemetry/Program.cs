// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.Metrics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OpenAI;
using OpenTelemetry;
using OpenTelemetry.Logs;
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

// Setup structured logging with OpenTelemetry
var serviceCollection = new ServiceCollection();
serviceCollection.AddLogging(loggingBuilder => loggingBuilder
    .SetMinimumLevel(LogLevel.Debug)
    .AddOpenTelemetry(options =>
    {
        options.SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"));
        options.AddOtlpExporter(otlpOptions =>
        {
            otlpOptions.Endpoint = new Uri(otlpEndpoint);
        });
        options.IncludeScopes = true;
        options.IncludeFormattedMessage = true;
    }));

var serviceProvider = serviceCollection.BuildServiceProvider();
var logger = serviceProvider.GetRequiredService<ILogger<Program>>();

using var activitySource = new ActivitySource(SourceName);
using var meter = new Meter(SourceName);

// Create custom metrics (similar to Python example)
var interactionCounter = meter.CreateCounter<int>("agent_interactions_total", description: "Total number of agent interactions");
var responseTimeHistogram = meter.CreateHistogram<double>("agent_response_time_seconds", description: "Agent response time in seconds");

Console.WriteLine("""
    === OpenTelemetry Aspire Demo ===
    This demo shows OpenTelemetry integration with the Agent Framework.
    You can view the telemetry data in the Aspire Dashboard.
    Type your message and press Enter. Type 'exit' or empty message to quit.
    """);

// Log application startup
logger.LogInformation("OpenTelemetry Aspire Demo application started");
logger.LogInformation("OTLP endpoint configured: {OtlpEndpoint}", otlpEndpoint);
logger.LogDebug("Service name: {ServiceName}, Source name: {SourceName}", ServiceName, SourceName);

// Create the chat client
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

logger.LogInformation("Initializing Azure OpenAI client with endpoint: {Endpoint}", endpoint);
logger.LogDebug("Using deployment: {DeploymentName}", deploymentName);

// Create a logger specifically for the agent
var loggerFactory = serviceProvider.GetRequiredService<ILoggerFactory>();

// Create the agent with OpenTelemetry instrumentation
logger.LogInformation("Creating Agent with OpenTelemetry instrumentation");

using var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
        .GetChatClient(deploymentName)
        .CreateAIAgent(
            name: "OpenTelemetryDemoAgent",
            instructions: "You are a helpful assistant that provides concise and informative responses.")
        .WithOpenTelemetry(loggerFactory, SourceName);

var thread = agent.GetNewThread();

logger.LogInformation("Agent created successfully with ID: {AgentId}", agent.Id);

// Create a parent span for the entire agent session
using var sessionActivity = activitySource.StartActivity("Agent Session");
var sessionId = thread.ConversationId ?? Guid.NewGuid().ToString();
sessionActivity?.SetTag("agent.name", "OpenTelemetryDemoAgent");
sessionActivity?.SetTag("session.id", sessionId);
sessionActivity?.SetTag("session.start_time", DateTimeOffset.UtcNow.ToString("O"));

logger.LogInformation("Starting agent session with ID: {SessionId}", sessionId);
using (logger.BeginScope(new Dictionary<string, object> { ["SessionId"] = sessionId, ["AgentName"] = "OpenTelemetryDemoAgent" }))
{
    var interactionCount = 0;

    while (true)
    {
        Console.Write("You: ");
        var userInput = Console.ReadLine();

        if (string.IsNullOrWhiteSpace(userInput) || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
        {
            logger.LogInformation("User requested to exit the session");
            break;
        }

        interactionCount++;
        logger.LogInformation("Processing user interaction #{InteractionNumber}: {UserInput}", interactionCount, userInput);

        // Create a child span for each individual interaction
        using var activity = activitySource.StartActivity("Agent Interaction");
        activity?.SetTag("user.input", userInput);
        activity?.SetTag("agent.name", "OpenTelemetryDemoAgent");
        activity?.SetTag("interaction.number", interactionCount);

        var stopwatch = System.Diagnostics.Stopwatch.StartNew();

        try
        {
            logger.LogDebug("Starting agent execution for interaction #{InteractionNumber}", interactionCount);
            Console.Write("Agent: ");

            // Run the agent (this will create its own internal telemetry spans)
            await foreach (var update in agent.RunStreamingAsync(userInput, thread))
            {
                Console.Write(update.Text);
            }

            Console.WriteLine();

            stopwatch.Stop();
            var responseTime = stopwatch.Elapsed.TotalSeconds;

            // Record metrics (similar to Python example)
            interactionCounter.Add(1, new KeyValuePair<string, object?>("status", "success"));
            responseTimeHistogram.Record(responseTime,
                new KeyValuePair<string, object?>("status", "success"));

            activity?.SetTag("response.success", true);

            logger.LogInformation("Agent interaction #{InteractionNumber} completed successfully in {ResponseTime:F2} seconds",
                interactionCount, responseTime);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error: {ex.Message}");
            Console.WriteLine();

            stopwatch.Stop();
            var responseTime = stopwatch.Elapsed.TotalSeconds;

            // Record error metrics
            interactionCounter.Add(1, new KeyValuePair<string, object?>("status", "error"));
            responseTimeHistogram.Record(responseTime,
                new KeyValuePair<string, object?>("status", "error"));

            activity?.SetTag("response.success", false);
            activity?.SetTag("error.message", ex.Message);
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);

            logger.LogError(ex, "Agent interaction #{InteractionNumber} failed after {ResponseTime:F2} seconds: {ErrorMessage}",
                interactionCount, responseTime, ex.Message);
        }
    }

    // Add session summary to the parent span
    sessionActivity?.SetTag("session.total_interactions", interactionCount);
    sessionActivity?.SetTag("session.end_time", DateTimeOffset.UtcNow.ToString("O"));

    logger.LogInformation("Agent session completed. Total interactions: {TotalInteractions}", interactionCount);
} // End of logging scope

logger.LogInformation("OpenTelemetry Aspire Demo application shutting down");
