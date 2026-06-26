// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Python-parity coverage for tracing (mirrors test_sse_streaming_uses_request_parent_span_context): the agent
/// run that backs a deferred SSE stream executes under the request's parent span, so the trace context is not
/// lost across the streaming boundary.
/// </summary>
public class ResponsesTracingParityTests
{
    [Fact]
    public async Task SseStreaming_RunsUnderRequestParentSpanAsync()
    {
        using var source = new ActivitySource("test.hosting.channels");
        using var listener = new ActivityListener
        {
            ShouldListenTo = s => s.Name == source.Name,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
        };
        ActivitySource.AddActivityListener(listener);

        var agent = new SpanCapturingAgent();
        ActivityTraceId requestTraceId = default;

        await using var app = await TestHostApp.StartAsync(
            b => b.AddAgentFrameworkHost(agent).AddResponsesChannel(),
            configureApp: app => app.Use(async (context, next) =>
            {
                using var activity = source.StartActivity("request");
                requestTraceId = Activity.Current!.TraceId;
                await next();
            }));

        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        await response.Content.ReadAsStringAsync();

        Assert.NotEqual(default, requestTraceId);
        Assert.Equal(requestTraceId, agent.ObservedTraceId);
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
