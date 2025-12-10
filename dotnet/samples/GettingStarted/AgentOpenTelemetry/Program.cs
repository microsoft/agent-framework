// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

#region Setup Telemetry

const string SourceName = "OpenTelemetryAspire.ConsoleApp";
const string ServiceName = "AgentOpenTelemetry";

// Configure OpenTelemetry for Aspire dashboard
var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4318";

var applicationInsightsConnectionString = Environment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");

// Create a resource to identify this service
var resource = ResourceBuilder.CreateDefault()
    .AddService(ServiceName, serviceVersion: "1.0.0")
    .AddAttributes(new Dictionary<string, object>
    {
        ["service.instance.id"] = Environment.MachineName,
        ["deployment.environment"] = "development"
    })
    .Build();

// Setup tracing with resource
var tracerProviderBuilder = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddSource(SourceName) // Our custom activity source
    .AddSource("*Microsoft.Agents.AI") // Agent Framework telemetry
    .AddHttpClientInstrumentation() // Capture HTTP calls to OpenAI
    .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint));

if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
{
    tracerProviderBuilder.AddAzureMonitorTraceExporter(options => options.ConnectionString = applicationInsightsConnectionString);
}

using var tracerProvider = tracerProviderBuilder.Build();

// Setup metrics with resource and instrument name filtering
using var meterProvider = Sdk.CreateMeterProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddMeter(SourceName) // Our custom meter
    .AddMeter("*Microsoft.Agents.AI") // Agent Framework metrics
    .AddHttpClientInstrumentation() // HTTP client metrics
    .AddRuntimeInstrumentation() // .NET runtime metrics
    .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint))
    .Build();

// Setup structured logging with OpenTelemetry
var serviceCollection = new ServiceCollection();
serviceCollection.AddLogging(loggingBuilder => loggingBuilder
    .SetMinimumLevel(LogLevel.Debug)
    .AddOpenTelemetry(options =>
    {
        options.SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"));
        options.AddOtlpExporter(otlpOptions => otlpOptions.Endpoint = new Uri(otlpEndpoint));
        if (!string.IsNullOrWhiteSpace(applicationInsightsConnectionString))
        {
            options.AddAzureMonitorLogExporter(options => options.ConnectionString = applicationInsightsConnectionString);
        }
        options.IncludeScopes = true;
        options.IncludeFormattedMessage = true;
    }));

using var activitySource = new ActivitySource(SourceName);
using var meter = new Meter(SourceName);

// Create custom metrics
var interactionCounter = meter.CreateCounter<int>("agent_interactions_total", description: "Total number of agent interactions");
var responseTimeHistogram = meter.CreateHistogram<double>("agent_response_time_seconds", description: "Agent response time in seconds");

#endregion

var serviceProvider = serviceCollection.BuildServiceProvider();
var loggerFactory = serviceProvider.GetRequiredService<ILoggerFactory>();
var appLogger = loggerFactory.CreateLogger<Program>();

Console.WriteLine("""
    === OpenTelemetry Aspire Demo ===
    This demo shows OpenTelemetry integration with the Agent Framework.
    You can view the telemetry data in the Aspire Dashboard.
    Type your message and press Enter. Type 'exit' or empty message to quit.
    """);

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Log application startup
appLogger.LogInformation("OpenTelemetry Aspire Demo application started");

[Description("Get the weather for a given location.")]
static async Task<string> GetWeatherAsync([Description("The location to get the weather for.")] string location)
{
    await Task.Delay(2000);
    return $"The weather in {location} is cloudy with a high of 15°C.";
}

using var instrumentedChatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
        .AsIChatClient() // Converts a native OpenAI SDK ChatClient into a Microsoft.Extensions.AI.IChatClient
        .AsBuilder()
        .UseFunctionInvocation()
        .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true) // enable telemetry at the chat client level
        .Build();

appLogger.LogInformation("Creating Agent with OpenTelemetry instrumentation");
// Create the agent with the instrumented chat client
var agent = new ChatClientAgent(instrumentedChatClient,
    name: "OpenTelemetryDemoAgent",
    instructions: "You are a helpful assistant that provides concise and informative responses.",
    tools: [AIFunctionFactory.Create(GetWeatherAsync)])
    .AsBuilder()
    .UseOpenTelemetry(SourceName, configure: (cfg) => cfg.EnableSensitiveData = true) // enable telemetry at the agent level
    .Build();

var thread = agent.GetNewThread();

appLogger.LogInformation("Agent created successfully with ID: {AgentId}", agent.Id);

// Create a parent span for the entire agent session
using var sessionActivity = activitySource.StartActivity("Agent Session");
Console.WriteLine($"Trace ID: {sessionActivity?.TraceId} ");

var sessionId = Guid.NewGuid().ToString("N");
sessionActivity?
    .SetTag("agent.name", "OpenTelemetryDemoAgent")
    .SetTag("session.id", sessionId)
    .SetTag("session.start_time", DateTimeOffset.UtcNow.ToString("O"));

appLogger.LogInformation("Starting agent session with ID: {SessionId}", sessionId);
using (appLogger.BeginScope(new Dictionary<string, object> { ["SessionId"] = sessionId, ["AgentName"] = "OpenTelemetryDemoAgent" }))
{
    var interactionCount = 0;

    while (true)
    {
        Console.Write("You (or 'exit' to quit): ");
        var userInput = Console.ReadLine();

        if (string.IsNullOrWhiteSpace(userInput) || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
        {
            appLogger.LogInformation("User requested to exit the session");
            break;
        }

        interactionCount++;
        appLogger.LogInformation("Processing user interaction #{InteractionNumber}: {UserInput}", interactionCount, userInput);

        // Create a child span for each individual interaction
        using var activity = activitySource.StartActivity("Agent Interaction");
        activity?
            .SetTag("user.input", userInput)
            .SetTag("agent.name", "OpenTelemetryDemoAgent")
            .SetTag("interaction.number", interactionCount);

        var stopwatch = Stopwatch.StartNew();

        try
        {
            appLogger.LogDebug("Starting agent execution for interaction #{InteractionNumber}", interactionCount);
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

            appLogger.LogInformation("Agent interaction #{InteractionNumber} completed successfully in {ResponseTime:F2} seconds",
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

            activity?
                .SetTag("response.success", false)
                .SetTag("error.message", ex.Message)
                .SetStatus(ActivityStatusCode.Error, ex.Message);

            appLogger.LogError(ex, "Agent interaction #{InteractionNumber} failed after {ResponseTime:F2} seconds: {ErrorMessage}",
                interactionCount, responseTime, ex.Message);
        }
    }

    // Add session summary to the parent span
    sessionActivity?
        .SetTag("session.total_interactions", interactionCount)
        .SetTag("session.end_time", DateTimeOffset.UtcNow.ToString("O"));

    appLogger.LogInformation("Agent session completed. Total interactions: {TotalInteractions}", interactionCount);
} // End of logging scope

appLogger.LogInformation("OpenTelemetry Aspire Demo application shutting down");
