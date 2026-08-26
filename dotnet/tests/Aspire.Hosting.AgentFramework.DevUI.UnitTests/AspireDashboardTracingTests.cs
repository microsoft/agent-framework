// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Aspire.Hosting.ApplicationModel;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Regression tests for forwarding Aspire Dashboard traces to DevUI.
/// </summary>
public class AspireDashboardTracingTests
{
    [Fact]
    public void SseResponseIdCapture_FragmentedResponseCreatedEvent_CapturesResponseId()
    {
        // Arrange
        var capture = new SseResponseIdCapture();

        // Act
        capture.Append(Encoding.UTF8.GetBytes("data: {\"type\":\"response.cre"));
        capture.Append(Encoding.UTF8.GetBytes("ated\",\"response\":{\"id\":\"resp_123\"}}\r"));
        capture.Append(Encoding.UTF8.GetBytes("\n\r\ndata: [DONE]\n\n"));

        // Assert
        Assert.Equal("resp_123", capture.ResponseId);
    }

    [Fact]
    public void SseResponseIdCapture_MalformedEvent_DoesNotDiscardLaterValidEvent()
    {
        // Arrange
        var capture = new SseResponseIdCapture();

        // Act
        capture.Append(Encoding.UTF8.GetBytes("data: {not-json}\n\n"));
        capture.Append(Encoding.UTF8.GetBytes("data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp_valid\"}}\n\n"));

        // Assert
        Assert.Equal("resp_valid", capture.ResponseId);
    }

    [Fact]
    public void ConvertToTraceEvents_OtlpSpan_PreservesHierarchyTimingAttributesAndError()
    {
        // Arrange
        using var document = JsonDocument.Parse("""
            {
              "resourceSpans": [{
                "scopeSpans": [{
                  "spans": [{
                    "traceId": "00112233445566778899aabbccddeeff",
                    "spanId": "0011223344556677",
                    "parentSpanId": "8899aabbccddeeff",
                    "name": "invoke_agent",
                    "startTimeUnixNano": "1000000000",
                    "endTimeUnixNano": "2500000000",
                    "attributes": [
                      {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "12"}},
                      {"key": "agent.name", "value": {"stringValue": "writer"}},
                      {"key": "cached", "value": {"boolValue": true}}
                    ],
                    "status": {"code": 2, "message": "model failed"},
                    "events": [{
                      "name": "exception",
                      "timeUnixNano": "2000000000",
                      "attributes": [{"key": "exception.type", "value": {"stringValue": "System.Exception"}}]
                    }]
                  }]
                }]
              }]
            }
            """);

        // Act
        var events = AspireDashboardTraceClient.ConvertToTraceEvents(
            document.RootElement,
            responseId: "resp_123",
            entityId: "writer-service/writer");

        // Assert
        var traceEvent = Assert.Single(events);
        Assert.Equal("response.trace.completed", traceEvent["type"]?.GetValue<string>());

        var data = traceEvent["data"]!.AsObject();
        Assert.Equal("trace_span", data["type"]?.GetValue<string>());
        Assert.Equal("00112233445566778899aabbccddeeff", data["trace_id"]?.GetValue<string>());
        Assert.Equal("0011223344556677", data["span_id"]?.GetValue<string>());
        Assert.Equal("8899aabbccddeeff", data["parent_span_id"]?.GetValue<string>());
        Assert.Equal("invoke_agent", data["operation_name"]?.GetValue<string>());
        Assert.Equal(1.0, data["start_time"]?.GetValue<double>());
        Assert.Equal(2.5, data["end_time"]?.GetValue<double>());
        Assert.Equal(1500.0, data["duration_ms"]?.GetValue<double>());
        Assert.Equal("ERROR", data["status"]?.GetValue<string>());
        Assert.Equal("model failed", data["error"]?.GetValue<string>());
        Assert.Equal("resp_123", data["response_id"]?.GetValue<string>());
        Assert.Equal("writer-service/writer", data["entity_id"]?.GetValue<string>());

        var attributes = data["attributes"]!.AsObject();
        Assert.Equal(12, attributes["gen_ai.usage.input_tokens"]?.GetValue<long>());
        Assert.Equal("writer", attributes["agent.name"]?.GetValue<string>());
        Assert.True(attributes["cached"]?.GetValue<bool>());

        var spanEvent = Assert.Single(data["events"]!.AsArray())!.AsObject();
        Assert.Equal("exception", spanEvent["name"]?.GetValue<string>());
        Assert.Equal(2.0, spanEvent["timestamp"]?.GetValue<double>());
        Assert.Equal(
            "System.Exception",
            spanEvent["attributes"]?["exception.type"]?.GetValue<string>());
    }

    [Fact]
    public async Task GetTraceEventsAsync_UsesScopedFiltersAndKeepsDashboardKeyServerSide()
    {
        // Arrange
        HttpRequestMessage? observedRequest = null;
        using var client = new HttpClient(new StubHttpMessageHandler(request =>
        {
            observedRequest = request;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""
                    {
                      "data": {
                        "resourceSpans": [{
                          "scopeSpans": [{
                            "spans": [{
                              "traceId": "00112233445566778899aabbccddeeff",
                              "spanId": "0011223344556677",
                              "name": "invoke_agent"
                            }]
                          }]
                        }]
                      },
                      "totalCount": 1,
                      "returnedCount": 1
                    }
                    """, Encoding.UTF8, "application/json")
            };
        }));

        // Act
        var events = await AspireDashboardTraceClient.GetTraceEventsAsync(
            client,
            new Uri("https://localhost:18888"),
            "dashboard-secret",
            "writer service",
            "00112233445566778899aabbccddeeff",
            "resp_123",
            "writer-service/writer",
            CancellationToken.None);

        // Assert
        Assert.NotNull(events);
        Assert.Single(events);
        Assert.NotNull(observedRequest);
        Assert.Equal(
            "/api/telemetry/spans?resource=writer%20service&traceId=00112233445566778899aabbccddeeff",
            observedRequest.RequestUri?.PathAndQuery);
        Assert.Equal("dashboard-secret", Assert.Single(observedRequest.Headers.GetValues("x-api-key")));
        Assert.DoesNotContain("dashboard-secret", observedRequest.RequestUri?.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetTraceEventsAsync_DashboardFailure_ReturnsUnavailableWithoutThrowing()
    {
        // Arrange
        using var client = new HttpClient(new StubHttpMessageHandler(_ =>
            new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)));

        // Act
        var events = await AspireDashboardTraceClient.GetTraceEventsAsync(
            client,
            new Uri("https://localhost:18888"),
            "dashboard-secret",
            "writer-service",
            "00112233445566778899aabbccddeeff",
            "resp_123",
            "writer-service/writer",
            CancellationToken.None);

        // Assert
        Assert.Null(events);
    }

    [Fact]
    public void SseResponseIdCapture_ConcurrentStreams_RemainIsolated()
    {
        // Arrange
        var capturedIds = new ConcurrentBag<string>();

        // Act
        Parallel.For(0, 100, index =>
        {
            var capture = new SseResponseIdCapture();
            capture.Append(Encoding.UTF8.GetBytes($"data: {{\"response\":{{\"id\":\"resp_{index}\"}}}}\n\n"));
            capturedIds.Add(capture.ResponseId!);
        });

        // Assert
        Assert.Equal(100, capturedIds.Distinct().Count());
    }

    [Fact]
    public void TryResolveDashboardConnection_AppHostUrls_UsesLoopbackEndpointAndApiKey()
    {
        // Arrange
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_URLS"] = "https://localhost:16500;http://localhost:16501",
                ["AppHost:DashboardApiKey"] = "dashboard-secret"
            })
            .Build();
        var aggregator = new DevUIAggregatorHostedService(
            new DevUIResource("test-devui"),
            NullLogger.Instance,
            configuration);

        // Act
        var resolved = aggregator.TryResolveDashboardConnection(out var dashboardBaseUri, out var dashboardApiKey);

        // Assert
        Assert.True(resolved);
        Assert.Equal(new Uri("https://localhost:16500"), dashboardBaseUri);
        Assert.Equal("dashboard-secret", dashboardApiKey);
    }

    [Fact]
    public void TryResolveDashboardConnection_NonLoopbackUrl_DoesNotExposeApiKey()
    {
        // Arrange
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_URLS"] = "https://example.com:16500",
                ["AppHost:DashboardApiKey"] = "dashboard-secret"
            })
            .Build();
        var aggregator = new DevUIAggregatorHostedService(
            new DevUIResource("test-devui"),
            NullLogger.Instance,
            configuration);

        // Act
        var resolved = aggregator.TryResolveDashboardConnection(out _, out var dashboardApiKey);

        // Assert
        Assert.False(resolved);
        Assert.Null(dashboardApiKey);
    }

    [Fact]
    public async Task Aggregator_ResponseTraceFlow_PropagatesTraceAndReturnsDashboardSpansAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync();
        using var metaResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        metaResponse.EnsureSuccessStatusCode();
        using var request = new HttpRequestMessage(HttpMethod.Post, "/v1/responses")
        {
            Content = new StringContent(
                """{"metadata":{"entity_id":"writer-service/writer"},"input":"hello","stream":true}""",
                Encoding.UTF8,
                "application/json")
        };

        // Act
        using var response = await context.Client.SendAsync(request);
        var responseBody = await response.Content.ReadAsStringAsync();
        using var tracesResponse = await context.Client.GetAsync(new Uri("/v1/responses/resp_integration/traces", UriKind.Relative));
        using var tracesDocument = JsonDocument.Parse(await tracesResponse.Content.ReadAsStreamAsync());

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("resp_integration", responseBody, StringComparison.Ordinal);
        Assert.NotNull(context.AgentTraceParent);
        Assert.Matches("^00-[0-9a-f]{32}-[0-9a-f]{16}-01$", context.AgentTraceParent);
        Assert.Equal("dashboard-secret", context.DashboardApiKey);
        Assert.Equal(context.AgentTraceParent![3..35], context.DashboardTraceId);
        Assert.Equal("writer-service", context.DashboardResourceName);
        Assert.Equal(HttpStatusCode.OK, tracesResponse.StatusCode);
        Assert.Equal(
            "response.trace.completed",
            tracesDocument.RootElement.GetProperty("data")[0].GetProperty("type").GetString());
    }

    [Fact]
    public async Task Aggregator_ResponseBeforeMeta_StillPropagatesTraceAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync();
        using var request = CreateAgentRequest("resp_before_meta");

        // Act
        using var response = await context.Client.SendAsync(request);
        await response.Content.LoadIntoBufferAsync();
        using var tracesResponse = await context.Client.GetAsync(
            new Uri("/v1/responses/resp_before_meta/traces", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(HttpStatusCode.OK, tracesResponse.StatusCode);
        Assert.Equal(0, context.DashboardResourceProbeCount);
        Assert.Equal(context.AgentTraceParents["resp_before_meta"][3..35], context.DashboardTraceId);
    }

    [Fact]
    public async Task Aggregator_MetaProbeSuccess_IsLatchedAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync();

        // Act
        using var firstResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        using var firstDocument = JsonDocument.Parse(await firstResponse.Content.ReadAsStreamAsync());
        context.FailDashboardResourceProbe();
        using var secondResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        using var secondDocument = JsonDocument.Parse(await secondResponse.Content.ReadAsStreamAsync());

        // Assert
        Assert.True(firstDocument.RootElement.GetProperty("capabilities").GetProperty("trace_retrieval").GetBoolean());
        Assert.True(secondDocument.RootElement.GetProperty("capabilities").GetProperty("trace_retrieval").GetBoolean());
        Assert.Equal(1, context.DashboardResourceProbeCount);
    }

    [Fact]
    public async Task Aggregator_NonStreamingResponse_CapturesResponseIdAndReturnsTracesAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync();
        using var metaResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        metaResponse.EnsureSuccessStatusCode();
        using var request = CreateAgentRequest("resp_non_streaming", streaming: false);

        // Act
        using var response = await context.Client.SendAsync(request);
        using var responseDocument = JsonDocument.Parse(await response.Content.ReadAsStreamAsync());
        using var tracesResponse = await context.Client.GetAsync(
            new Uri("/v1/responses/resp_non_streaming/traces", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("resp_non_streaming", responseDocument.RootElement.GetProperty("id").GetString());
        Assert.Equal(HttpStatusCode.OK, tracesResponse.StatusCode);
        Assert.Equal(context.AgentTraceParents["resp_non_streaming"][3..35], context.DashboardTraceId);
    }

    [Fact]
    public async Task Aggregator_DashboardTraceTimeout_ReturnsServiceUnavailableAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync(dashboardTraceTimeout: true);
        using var metaResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        metaResponse.EnsureSuccessStatusCode();
        using var request = CreateAgentRequest("resp_dashboard_timeout");
        using var response = await context.Client.SendAsync(request);
        await response.Content.LoadIntoBufferAsync();

        // Act
        using var tracesResponse = await context.Client.GetAsync(
            new Uri("/v1/responses/resp_dashboard_timeout/traces", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, tracesResponse.StatusCode);
    }

    [Fact]
    public async Task Aggregator_DashboardUnavailable_DoesNotBreakAgentResponseAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync(dashboardUnavailable: true);
        using var metaResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        metaResponse.EnsureSuccessStatusCode();
        using var request = CreateAgentRequest("resp_dashboard_down");

        // Act
        using var response = await context.Client.SendAsync(request);
        var responseBody = await response.Content.ReadAsStringAsync();
        using var tracesResponse = await context.Client.GetAsync(
            new Uri("/v1/responses/resp_dashboard_down/traces", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("resp_dashboard_down", responseBody, StringComparison.Ordinal);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, tracesResponse.StatusCode);
    }

    [Fact]
    public async Task Aggregator_ConcurrentResponses_DoNotCrossWireTraceIdsAsync()
    {
        // Arrange
        await using var context = await TracingProxyTestContext.StartAsync();
        using var metaResponse = await context.Client.GetAsync(new Uri("/meta", UriKind.Relative));
        metaResponse.EnsureSuccessStatusCode();
        var responseIds = Enumerable.Range(0, 12).Select(index => $"resp_concurrent_{index}").ToArray();

        // Act
        await Task.WhenAll(responseIds.Select(async responseId =>
        {
            using var request = CreateAgentRequest(responseId);
            using var response = await context.Client.SendAsync(request);
            response.EnsureSuccessStatusCode();
            await response.Content.LoadIntoBufferAsync();
        }));

        var traceIds = new ConcurrentDictionary<string, string>();
        await Task.WhenAll(responseIds.Select(async responseId =>
        {
            using var response = await context.Client.GetAsync(
                new Uri($"/v1/responses/{responseId}/traces", UriKind.Relative));
            response.EnsureSuccessStatusCode();
            using var document = JsonDocument.Parse(await response.Content.ReadAsStreamAsync());
            var data = document.RootElement.GetProperty("data")[0].GetProperty("data");
            Assert.Equal(responseId, data.GetProperty("response_id").GetString());
            traceIds[responseId] = data.GetProperty("trace_id").GetString()!;
        }));

        // Assert
        Assert.Equal(responseIds.Length, traceIds.Values.Distinct().Count());
        foreach (var responseId in responseIds)
        {
            Assert.Equal(context.AgentTraceParents[responseId][3..35], traceIds[responseId]);
        }
    }

    private static HttpRequestMessage CreateAgentRequest(string responseId, bool streaming = true)
        => new(HttpMethod.Post, "/v1/responses")
        {
            Content = new StringContent(
                $$"""{"metadata":{"entity_id":"writer-service/writer","test_response_id":"{{responseId}}"},"input":"hello","stream":{{(streaming ? "true" : "false")}}}""",
                Encoding.UTF8,
                "application/json")
        };

    private sealed class StubHttpMessageHandler(Func<HttpRequestMessage, HttpResponseMessage> handler) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => Task.FromResult(handler(request));
    }

    private sealed class TracingProxyTestContext : IAsyncDisposable
    {
        private readonly WebApplication _agentBackend;
        private readonly WebApplication _dashboard;
        private readonly DevUIAggregatorHostedService _aggregator;
        private int _dashboardResourceProbeCount;
        private volatile bool _failDashboardResourceProbe;

        private TracingProxyTestContext(
            WebApplication agentBackend,
            WebApplication dashboard,
            DevUIAggregatorHostedService aggregator,
            HttpClient client)
        {
            this._agentBackend = agentBackend;
            this._dashboard = dashboard;
            this._aggregator = aggregator;
            this.Client = client;
        }

        public HttpClient Client { get; }

        public string? AgentTraceParent { get; private set; }

        public ConcurrentDictionary<string, string> AgentTraceParents { get; } = new(StringComparer.Ordinal);

        public string? DashboardApiKey { get; private set; }

        public string? DashboardTraceId { get; private set; }

        public string? DashboardResourceName { get; private set; }

        public int DashboardResourceProbeCount => Volatile.Read(ref this._dashboardResourceProbeCount);

        public void FailDashboardResourceProbe() => this._failDashboardResourceProbe = true;

        public static async Task<TracingProxyTestContext> StartAsync(
            bool dashboardUnavailable = false,
            bool dashboardTraceTimeout = false)
        {
            var agentBackend = CreateWebApplication();
            var dashboard = CreateWebApplication();
            TracingProxyTestContext? testContext = null;

            agentBackend.MapPost("/v1/responses", async context =>
            {
                using var requestDocument = await JsonDocument.ParseAsync(context.Request.Body, cancellationToken: context.RequestAborted);
                var responseId = requestDocument.RootElement
                    .GetProperty("metadata")
                    .TryGetProperty("test_response_id", out var configuredResponseId)
                        ? configuredResponseId.GetString()!
                        : "resp_integration";
                var traceParent = context.Request.Headers.TraceParent.FirstOrDefault();
                testContext!.AgentTraceParent = traceParent;
                testContext.AgentTraceParents[responseId] = traceParent!;

                if (requestDocument.RootElement.TryGetProperty("stream", out var stream) && !stream.GetBoolean())
                {
                    await context.Response.WriteAsJsonAsync(
                        new { id = responseId, output = Array.Empty<object>() },
                        context.RequestAborted);
                    return;
                }

                context.Response.ContentType = "text/event-stream";
                await context.Response.WriteAsync(
                    $"data: {{\"type\":\"response.created\",\"response\":{{\"id\":\"{responseId}\"}}}}\n\n",
                    context.RequestAborted);
                await context.Response.WriteAsync("data: [DONE]\n\n", context.RequestAborted);
            });

            dashboard.MapGet("/api/telemetry/spans", async Task<IResult> (HttpContext context) =>
            {
                var dashboardApiKey = context.Request.Headers["x-api-key"].FirstOrDefault();
                var dashboardTraceId = context.Request.Query["traceId"].FirstOrDefault();
                var dashboardResourceName = context.Request.Query["resource"].FirstOrDefault();
                testContext!.DashboardApiKey = dashboardApiKey;
                testContext.DashboardTraceId = dashboardTraceId;
                testContext.DashboardResourceName = dashboardResourceName;

                if (dashboardUnavailable)
                {
                    return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
                }

                if (dashboardTraceTimeout)
                {
                    await Task.Delay(Timeout.InfiniteTimeSpan, context.RequestAborted);
                    return Results.Empty;
                }

                return Results.Json(new
                {
                    data = new
                    {
                        resourceSpans = new[]
                        {
                            new
                            {
                                scopeSpans = new[]
                                {
                                    new
                                    {
                                        spans = new[]
                                        {
                                            new
                                            {
                                                traceId = dashboardTraceId,
                                                spanId = "0011223344556677",
                                                name = "invoke_agent"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    totalCount = 1,
                    returnedCount = 1
                });
            });
            dashboard.MapGet("/api/telemetry/resources", () =>
            {
                Interlocked.Increment(ref testContext!._dashboardResourceProbeCount);
                return testContext._failDashboardResourceProbe
                    ? Results.StatusCode(StatusCodes.Status503ServiceUnavailable)
                    : Results.Json(Array.Empty<object>());
            });

            await agentBackend.StartAsync();
            await dashboard.StartAsync();

            var resource = new DevUIResource("test-devui");
            resource.Annotations.Add(new AgentServiceAnnotation(CreateBackendResource("writer-service", GetBaseAddress(agentBackend))));

            var loggerFactory = LoggerFactory.Create(_ => { });
            var aggregator = new DevUIAggregatorHostedService(
                resource,
                loggerFactory.CreateLogger<DevUIAggregatorHostedService>(),
                dashboardConnectionOverride: new AspireDashboardConnection(
                    new Uri(GetBaseAddress(dashboard)),
                    "dashboard-secret"));
            await aggregator.StartAsync(CancellationToken.None);

            testContext = new TracingProxyTestContext(
                agentBackend,
                dashboard,
                aggregator,
                new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{aggregator.AllocatedPort}") });
            return testContext;
        }

        public async ValueTask DisposeAsync()
        {
            this.Client.Dispose();
            await this._aggregator.DisposeAsync();
            await this._agentBackend.StopAsync();
            await this._agentBackend.DisposeAsync();
            await this._dashboard.StopAsync();
            await this._dashboard.DisposeAsync();
        }

        private static WebApplication CreateWebApplication()
        {
            var builder = WebApplication.CreateSlimBuilder();
            builder.Logging.ClearProviders();
            var app = builder.Build();
            app.Urls.Add("http://127.0.0.1:0");
            return app;
        }

        private static TestBackendResource CreateBackendResource(string name, string backendUrl)
        {
            var backendUri = new Uri(backendUrl);
            var resource = new TestBackendResource(name);
            var endpoint = new EndpointAnnotation(
                ProtocolType.Tcp,
                uriScheme: backendUri.Scheme,
                name: "http",
                port: backendUri.Port,
                isProxied: false)
            {
                TargetHost = backendUri.Host
            };
            endpoint.AllocatedEndpoint = new AllocatedEndpoint(endpoint, backendUri.Host, backendUri.Port);
            resource.Annotations.Add(endpoint);
            return resource;
        }

        private static string GetBaseAddress(WebApplication app)
        {
            var addresses = app.Services.GetRequiredService<IServer>()
                .Features.Get<IServerAddressesFeature>()!;
            return addresses.Addresses.Single();
        }

        private sealed class TestBackendResource(string name) : Resource(name), IResourceWithEndpoints;
    }
}
