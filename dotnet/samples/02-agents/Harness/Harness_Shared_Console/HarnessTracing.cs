// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable VSTHRD002 // Synchronous waits are required by OpenTelemetry enrichment callbacks.

using OpenTelemetry;
using OpenTelemetry.Trace;

namespace Harness.Shared.Console;

/// <summary>
/// Provides factory methods for creating pre-configured OpenTelemetry tracing for harness samples.
/// </summary>
public static class HarnessTracing
{
    /// <summary>
    /// Creates a <see cref="TracerProvider"/> that captures spans from the specified source and HTTP client activity,
    /// enriching HTTP spans with full request/response headers and bodies, and exports all spans to a timestamped
    /// text file in the application base directory.
    /// </summary>
    /// <param name="sourceName">The activity source name to subscribe to (e.g., "Harness.Research").</param>
    /// <returns>A configured <see cref="TracerProvider"/>, or <see langword="null"/> if the builder returns null.</returns>
    public static TracerProvider? CreateFileTracerProvider(string sourceName)
    {
        var traceLogPath = Path.Combine(AppContext.BaseDirectory, $"traces_{DateTime.UtcNow:yyyyMMdd_HHmmss}_{Guid.NewGuid()}.log");

        return Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddHttpClientInstrumentation((options) =>
            {
                options.EnrichWithHttpRequestMessage = (activity, request) =>
                {
                    activity.SetTag("http.request.headers", request.Headers.ToString());
                    if (request.Content != null)
                    {
                        activity.SetTag("http.request.content.headers", request.Content.Headers.ToString());
                        var content = request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                        activity.SetTag("http.request.content.body", content);
                    }
                };

                options.EnrichWithHttpResponseMessage = (activity, response) =>
                {
                    activity.SetTag("http.response.headers", response.Headers.ToString());
                    if (response.Content != null)
                    {
                        activity.SetTag("http.response.content.headers", response.Content.Headers.ToString());
                        var content = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                        activity.SetTag("http.response.content.body", content);
                    }
                };
            })
            .AddProcessor(new SimpleActivityExportProcessor(new FileSpanExporter(traceLogPath)))
            .Build();
    }
}
