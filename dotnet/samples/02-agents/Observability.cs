// Copyright (c) Microsoft. All rights reserved.

// Observability with OpenTelemetry
// Add tracing, metrics, and structured logging to your agent using OpenTelemetry.
// Telemetry data can be viewed in Aspire Dashboard or Azure Monitor.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/observability

using System.ComponentModel;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

// <setup_telemetry>
const string SourceName = "OpenTelemetryAspire.ConsoleApp";
const string ServiceName = "AgentOpenTelemetry";

var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4318";

using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddSource(SourceName)
    .AddSource("*Microsoft.Agents.AI")
    .AddHttpClientInstrumentation()
    .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint))
    .Build();

using var meterProvider = Sdk.CreateMeterProviderBuilder()
    .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"))
    .AddMeter(SourceName)
    .AddMeter("*Microsoft.Agents.AI")
    .AddHttpClientInstrumentation()
    .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint))
    .Build();

var serviceCollection = new ServiceCollection();
serviceCollection.AddLogging(loggingBuilder => loggingBuilder
    .SetMinimumLevel(LogLevel.Debug)
    .AddOpenTelemetry(options =>
    {
        options.SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0"));
        options.AddOtlpExporter(otlpOptions => otlpOptions.Endpoint = new Uri(otlpEndpoint));
        options.IncludeScopes = true;
        options.IncludeFormattedMessage = true;
    }));

using var activitySource = new ActivitySource(SourceName);
// </setup_telemetry>

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static async Task<string> GetWeatherAsync([Description("The location to get the weather for.")] string location)
{
    await Task.Delay(2000);
    return $"The weather in {location} is cloudy with a high of 15°C.";
}

// <create_instrumented_agent>
using var instrumentedChatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
        .AsIChatClient()
        .AsBuilder()
        .UseFunctionInvocation()
        .UseOpenTelemetry(sourceName: SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
        .Build();

var agent = new ChatClientAgent(instrumentedChatClient,
    name: "OpenTelemetryDemoAgent",
    instructions: "You are a helpful assistant that provides concise and informative responses.",
    tools: [AIFunctionFactory.Create(GetWeatherAsync)])
    .AsBuilder()
    .UseOpenTelemetry(SourceName, configure: (cfg) => cfg.EnableSensitiveData = true)
    .Build();
// </create_instrumented_agent>

// <run_instrumented_agent>
var session = await agent.CreateSessionAsync();

using var sessionActivity = activitySource.StartActivity("Agent Session");
sessionActivity?.SetTag("agent.name", "OpenTelemetryDemoAgent");

await foreach (var update in agent.RunStreamingAsync("What's the weather in Seattle?", session))
{
    Console.Write(update.Text);
}
Console.WriteLine();
// </run_instrumented_agent>
