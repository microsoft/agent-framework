// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.Metrics;
using ClawAgent;
using Harness.Shared.Console;
using Harness.Shared.Console.OpenAI;
using Harness.Shared.Console.ToolFormatters;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

const string ServiceName = "ClawAgent.Console";
var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT");
var telemetryEnabled = !string.IsNullOrWhiteSpace(otlpEndpoint);

// Export telemetry only when an OTLP endpoint is configured. We deliberately avoid the
// console exporter: this is an interactive app whose UI is rendered by
// HarnessConsole.RunAgentAsync, and streaming spans/metrics to stdout corrupts that UI.
var resourceBuilder = ResourceBuilder.CreateDefault().AddService(ServiceName, serviceVersion: "1.0.0");
using var tracerProvider = telemetryEnabled
    ? Sdk.CreateTracerProviderBuilder()
        .SetResourceBuilder(resourceBuilder)
        .AddSource(ClawAgentFactory.OpenTelemetrySourceName)
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint!))
        .Build()
    : null;

using var meterProvider = telemetryEnabled
    ? Sdk.CreateMeterProviderBuilder()
        .SetResourceBuilder(resourceBuilder)
        .AddMeter(ClawAgentFactory.OpenTelemetrySourceName)
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()
        .AddOtlpExporter(options => options.Endpoint = new Uri(otlpEndpoint!))
        .Build()
    : null;

if (!telemetryEnabled)
{
    Console.WriteLine("Telemetry export is off. Set OTEL_EXPORTER_OTLP_ENDPOINT to send traces/metrics to an OTLP collector.");
}

using var meter = new Meter(ClawAgentFactory.OpenTelemetrySourceName);
var sessionCounter = meter.CreateCounter<int>("claw_console_sessions_total", description: "Interactive claw console sessions started.");
sessionCounter.Add(1);

await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    Log = Console.WriteLine,
});

await HarnessConsole.RunAgentAsync(
    build.Agent,
    userPrompt: "Ask me to value a stock, score your portfolio risk, research some tickers, or tidy your trade confirmations.",
    new HarnessConsoleOptions
    {
        Observers =
        [
            new OpenAIResponsesWebSearchDisplayObserver(),
            new OpenAIResponsesErrorObserver(),
            .. HarnessConsoleOptions.BuildObserversWithPlanning(
                build.Agent,
                planModeName: "plan",
                executionModeName: "execute",
                toolFormatters: ToolCallFormatter.BuildDefaultToolFormatters()),
        ],
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(build.Agent),
    });
