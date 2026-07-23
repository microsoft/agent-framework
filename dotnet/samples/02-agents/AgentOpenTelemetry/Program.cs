// Copyright (c) Microsoft. All rights reserved.

// In the samples build, the global `Environment` alias resolves to SampleHelpers.SampleEnvironment,
// which interactively prompts the user when a variable is missing. Use System.Environment directly
// for all reads here so that missing optional/detection variables return null silently.
using SystemEnvironment = System.Environment;

using System.ClientModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using Azure.AI.OpenAI;
using Azure.AI.Projects;
using OpenAI.Chat;
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

// Source name for this sample's custom ActivitySource and Meter; other instrumentation uses their own sources/categories.
const string SourceName = "OpenTelemetryAspire.ConsoleApp";
const string ServiceName = "AgentOpenTelemetry";

// Configure OpenTelemetry for Aspire dashboard
var otlpEndpoint = SystemEnvironment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4317";

var applicationInsightsConnectionString = SystemEnvironment.GetEnvironmentVariable("APPLICATIONINSIGHTS_CONNECTION_STRING");

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
    .AddMeter(SourceName) // Our custom meter source
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

// Log application startup
appLogger.LogInformation("OpenTelemetry Aspire Demo application started");

[Description("Get the weather for a given location.")]
static async Task<string> GetWeatherAsync([Description("The location to get the weather for.")] string location)
{
    await Task.Delay(2000);
    return $"The weather in {location} is cloudy with a high of 15°C.";
}

appLogger.LogInformation("Creating Agent with OpenTelemetry instrumentation");

// Auth/model selection precedence:
//   A. Preferred (default): Microsoft Foundry via DefaultAzureCredential
//      Requires: FOUNDRY_PROJECT_ENDPOINT. Run `az login` first.
//      If FOUNDRY_MODEL is not set, defaults to gpt-5-mini.
//   B. Fallback (local/dev): Azure OpenAI endpoint + API key — no az login required.
//      Requires: AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY.
//      If AZURE_OPENAI_DEPLOYMENT_NAME is not set, defaults to gpt-5-mini.
//   When both are configured, Foundry takes precedence.

const string DefaultModel = "gpt-5-mini";

var foundryEndpoint = SystemEnvironment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
var azureOpenAIEndpoint = SystemEnvironment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT");
var azureOpenAIApiKey = SystemEnvironment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
var azureOpenAIDeployment = SystemEnvironment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME");

AIAgent agent;

if (!string.IsNullOrWhiteSpace(foundryEndpoint))
{
    // Option A (Preferred): Microsoft Foundry with DefaultAzureCredential — requires az login
    var foundryModel = SystemEnvironment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? DefaultModel;

    appLogger.LogInformation("Mode: Foundry. Endpoint: {Endpoint}, Model: {Model}", foundryEndpoint, foundryModel);

    // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
    // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
    // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
    agent = new AIProjectClient(new Uri(foundryEndpoint), new DefaultAzureCredential())
        .AsAIAgent(
            model: foundryModel,
            instructions: "You are a helpful assistant that provides concise and informative responses.",
            name: "OpenTelemetryDemoAgent",
            tools: [AIFunctionFactory.Create(GetWeatherAsync)],
            clientFactory: client => client
                .AsBuilder()
                .UseFunctionInvocation()
                .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
                .Build())
        .AsBuilder()
        .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
        .Build();
}
else if (!string.IsNullOrWhiteSpace(azureOpenAIEndpoint)
    && !string.IsNullOrWhiteSpace(azureOpenAIApiKey))
{
    // Option B (Fallback): Azure OpenAI with API key — no az login required (local/dev convenience)
    var deploymentName = azureOpenAIDeployment ?? DefaultModel;
    appLogger.LogInformation("Mode: Azure OpenAI (API key). Endpoint: {Endpoint}, Deployment: {Deployment}", azureOpenAIEndpoint, deploymentName);

    agent = new AzureOpenAIClient(new Uri(azureOpenAIEndpoint), new ApiKeyCredential(azureOpenAIApiKey))
        .GetChatClient(deploymentName)
        .AsAIAgent(
            instructions: "You are a helpful assistant that provides concise and informative responses.",
            name: "OpenTelemetryDemoAgent",
            tools: [AIFunctionFactory.Create(GetWeatherAsync)],
            clientFactory: client => client
                .AsBuilder()
                .UseFunctionInvocation()
                .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
                .Build())
        .AsBuilder()
        .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
        .Build();
}
else
{
    throw new InvalidOperationException(
        """
        No valid configuration found. Set one of the following:

        Option A — Microsoft Foundry (recommended):
          FOUNDRY_PROJECT_ENDPOINT=https://<project>.services.ai.azure.com/api/projects/<project>
          FOUNDRY_MODEL=<model-deployment-name>   # optional; defaults to gpt-5-mini
          Then authenticate (e.g., az login)

        Option B — Azure OpenAI API key (local/dev fallback):
          AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
          AZURE_OPENAI_API_KEY=<your-api-key>
          AZURE_OPENAI_DEPLOYMENT_NAME=<deployment-name>   # if not set, defaults to gpt-5-mini
        """);
}

var session = await agent.CreateSessionAsync();

appLogger.LogInformation("Agent created successfully with ID: {AgentId}", agent.Id);

// When OTEL_DEMO_NEW_TRACE_PER_TURN=true, each interaction starts a new root trace (new TraceId)
// to make turns show up as standalone entries in dashboards. Session-level correlation is retained
// via the shared session.id tag (not via parent/child trace relationships).
// Default (false): interactions are child spans of the session span, preserving full trace correlation.
var newTracePerTurn = string.Equals(
    SystemEnvironment.GetEnvironmentVariable("OTEL_DEMO_NEW_TRACE_PER_TURN"),
    "true",
    StringComparison.OrdinalIgnoreCase);

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

        // If OTEL_DEMO_NEW_TRACE_PER_TURN is enabled, create a fresh ActivityContext with a new random
        // TraceId so each interaction appears as an independent root trace in the dashboard.
        // Passing `default` does NOT work — an empty ActivityContext causes the runtime to fall back
        // to Activity.Current (the session span), so all turns would still share the same TraceId.
        // Using a real random context guarantees a new TraceId without mutating Activity.Current.
        using var activity = newTracePerTurn
            ? activitySource.StartActivity("Agent Interaction", ActivityKind.Internal,
                new ActivityContext(ActivityTraceId.CreateRandom(), ActivitySpanId.CreateRandom(), ActivityTraceFlags.Recorded))
            : activitySource.StartActivity("Agent Interaction");
        activity?
            .SetTag("user.input", userInput)
            .SetTag("agent.name", "OpenTelemetryDemoAgent")
            .SetTag("session.id", sessionId)
            .SetTag("interaction.number", interactionCount);

        var stopwatch = Stopwatch.StartNew();

        try
        {
            appLogger.LogDebug("Starting agent execution for interaction #{InteractionNumber}", interactionCount);
            Console.Write("Agent: ");

            // Run the agent (this will create its own internal telemetry spans)
            await foreach (var update in agent.RunStreamingAsync(userInput, session))
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
