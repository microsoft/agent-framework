// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.ServerSentEvents;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class EndpointRouteBuilderExtensionsTests
{
    // ── /readiness auto-mapping (Foundry container-image-spec §2) ────────────────

    [Fact]
    public async Task MapFoundryResponses_MapsReadinessEndpoint_WhenTier3HostHasNotMappedItAsync()
    {
        // Arrange: Tier 3 host (WebApplication.CreateBuilder, no AgentHost) — Core SDK does
        // NOT map /readiness in this case, so MapFoundryResponses must cover the gap.
        using var host = await BuildTestHostAsync(static app => app.MapFoundryResponses());

        // Act
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task MapFoundryResponses_DoesNotDuplicateReadiness_WhenAlreadyMappedAsync()
    {
        // Arrange: developer already mapped /readiness with a custom body. The auto-map
        // must detect the existing route and leave it untouched (no AmbiguousMatchException
        // at runtime, no override of the developer's response).
        const string CustomBody = "ready-from-developer";
        using var host = await BuildTestHostAsync(static app =>
        {
            app.MapGet("/readiness", () => Results.Text("ready-from-developer"));
            app.MapFoundryResponses();
        });

        // Act
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Equal(CustomBody, body);
    }

    [Fact]
    public async Task MapFoundryResponses_CalledTwice_StillOnlyMapsReadinessOnceAsync()
    {
        // Arrange: defensive coverage for callers that map the responses pipeline twice.
        using var host = await BuildTestHostAsync(static app =>
        {
            app.MapFoundryResponses();
            app.MapFoundryResponses();
        });

        // Act + Assert: a single GET /readiness must succeed without ambiguous-match throw.
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task MapFoundryResponses_HostedCreateWithoutCallId_ReturnsUnsupportedProtocolAsync()
    {
        // Arrange: configuration marks the TestServer as hosted without changing the process-wide
        // environment or starting the AgentServer hosted task infrastructure.
        using var host = await BuildTestHostAsync(
            static app => app.MapFoundryResponses(),
            static builder => builder.Configuration.AddInMemoryCollection(
                new Dictionary<string, string?>
                {
                    [ServiceCollectionExtensions.FoundryHostingEnvironmentKey] = "true",
                }));
        using var request = new HttpRequestMessage(HttpMethod.Post, "/responses")
        {
            Content = new StringContent(
                """{"model":"test-agent","input":"hello"}""",
                Encoding.UTF8,
                "application/json"),
        };

        // Act
        using var response = await host.GetTestClient().SendAsync(request);
        string body = await response.Content.ReadAsStringAsync();

        // Assert: reject before the request enters AgentServer's resilient task boundary, which
        // wraps handler exceptions and would otherwise turn the intended 501 into a generic 500.
        Assert.Equal(HttpStatusCode.NotImplemented, response.StatusCode);
        Assert.Equal("upstream", response.Headers.GetValues("x-platform-error-source").Single());
        Assert.Contains(HostedProtocolCompatibility.UnsupportedProtocolErrorCode, body, StringComparison.Ordinal);
        Assert.Contains("2.0.0", body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapFoundryResponses_StreamTrue_EmitsAllAnnotationKindsAsync()
    {
        // Arrange and Act
        var (statusCode, mediaType, body) = await InvokeResponsesEndpointAsync(stream: true);

        // Assert
        Assert.Equal(HttpStatusCode.OK, statusCode);
        Assert.Equal("text/event-stream", mediaType);

        var events = await ParseSseEventsAsync(body);
        var annotationEvents = events
            .Where(e => e.GetProperty("type").GetString() == "response.output_text.annotation.added")
            .Select(e => e.GetProperty("annotation"))
            .ToArray();
        AssertAnnotations(annotationEvents);

        var contentPartDone = Assert.Single(events, e => e.GetProperty("type").GetString() == "response.content_part.done");
        AssertAnnotations(contentPartDone.GetProperty("part"));

        var outputItemDone = Assert.Single(events, e => e.GetProperty("type").GetString() == "response.output_item.done");
        var outputText = Assert.Single(outputItemDone.GetProperty("item").GetProperty("content").EnumerateArray());
        AssertAnnotations(outputText);

        var completed = Assert.Single(events, e => e.GetProperty("type").GetString() == "response.completed");
        Assert.Equal("response.completed", events[^1].GetProperty("type").GetString());
        var completedOutputItem = Assert.Single(completed.GetProperty("response").GetProperty("output").EnumerateArray());
        var completedOutputText = Assert.Single(completedOutputItem.GetProperty("content").EnumerateArray());
        AssertAnnotations(completedOutputText);
    }

    [Fact]
    public async Task MapFoundryResponses_StreamFalse_ReturnsAllAnnotationKindsAsync()
    {
        // Arrange and Act
        var (statusCode, mediaType, body) = await InvokeResponsesEndpointAsync(stream: false);

        // Assert
        Assert.Equal(HttpStatusCode.OK, statusCode);
        Assert.Equal("application/json", mediaType);

        using var document = JsonDocument.Parse(body);
        var outputItem = Assert.Single(document.RootElement.GetProperty("output").EnumerateArray());
        var outputText = Assert.Single(outputItem.GetProperty("content").EnumerateArray());
        AssertAnnotations(outputText);
    }

    private static async Task<(HttpStatusCode StatusCode, string? MediaType, string Body)> InvokeResponsesEndpointAsync(bool stream)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        AIAgent agent = new ChatClientAgent(CreateAnnotationChatClient());
        builder.Services.AddFoundryResponses(agent, new TestAgentSessionStore());
        builder.Services.AddLogging();

        await using var app = builder.Build();
        app.MapFoundryResponses();
        await app.StartAsync();

        var testServer = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");
        using var client = testServer.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Post, "/responses")
        {
            Content = new StringContent(CreateRequestJson(stream), Encoding.UTF8, "application/json"),
        };
        // Separate storage partitions keep concurrent test hosts from deleting each other's temporary response files.
        request.Headers.Add("x-agent-user-id", Guid.NewGuid().ToString("N"));
        using var response = await client.SendAsync(request);
        var body = await response.Content.ReadAsStringAsync();
        return (response.StatusCode, response.Content.Headers.ContentType?.MediaType, body);
    }

    private static IChatClient CreateAnnotationChatClient()
    {
        var annotations = new AIAnnotation[]
        {
            new CitationAnnotation
            {
                Url = new Uri("https://example.com/doc"),
                Title = "Example Document",
                AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 }]
            },
            new CitationAnnotation
            {
                FileId = "file_1",
                Title = "report.pdf",
                RawRepresentation = new FileCitationMessageAnnotation("file_1", 1, "report.pdf")
            },
            new CitationAnnotation
            {
                FileId = "file_2",
                RawRepresentation = new FilePathMessageAnnotation("file_2", 2)
            },
            new CitationAnnotation
            {
                FileId = "file_3",
                Title = "chart.png",
                AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 6, EndIndex = 11 }],
                RawRepresentation = new ContainerFileCitationMessageAnnotation(
                    "container_1",
                    "file_3",
                    6,
                    11,
                    "chart.png")
            },
        };

        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() => ToAsyncEnumerableUpdatesAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "Hello sources") { MessageId = "msg_response" },
                new ChatResponseUpdate(
                    ChatRole.Assistant,
                    [new AIContent { Annotations = annotations }])
                {
                    MessageId = "msg_response"
                }));
        return client.Object;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableUpdatesAsync(
        params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    private static string CreateRequestJson(bool stream) => $$"""
        {
          "model": "test",
          "stream": {{(stream ? "true" : "false")}},
          "input": [
            {
              "type": "message",
              "id": "msg_request",
              "status": "completed",
              "role": "user",
              "content": [{ "type": "input_text", "text": "Hello" }]
            }
          ]
        }
        """;

    private static async Task<List<JsonElement>> ParseSseEventsAsync(string body)
    {
        var events = new List<JsonElement>();
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(body));
        await foreach (var item in SseParser.Create(stream).EnumerateAsync())
        {
            if (item.Data == "[DONE]")
            {
                continue;
            }

            using var document = JsonDocument.Parse(item.Data);
            Assert.Equal(document.RootElement.GetProperty("type").GetString(), item.EventType);
            events.Add(document.RootElement.Clone());
        }

        return events;
    }

    private static void AssertAnnotations(JsonElement outputText) =>
        AssertAnnotations(outputText.GetProperty("annotations").EnumerateArray().ToArray());

    private static void AssertAnnotations(IReadOnlyCollection<JsonElement> annotations)
    {
        Assert.Collection(
            annotations,
            annotation =>
            {
                Assert.Equal("url_citation", annotation.GetProperty("type").GetString());
                Assert.Equal("https://example.com/doc", annotation.GetProperty("url").GetString());
                Assert.Equal("Example Document", annotation.GetProperty("title").GetString());
                Assert.Equal(0, annotation.GetProperty("start_index").GetInt64());
                Assert.Equal(5, annotation.GetProperty("end_index").GetInt64());
            },
            annotation =>
            {
                Assert.Equal("file_citation", annotation.GetProperty("type").GetString());
                Assert.Equal("file_1", annotation.GetProperty("file_id").GetString());
                Assert.Equal(1, annotation.GetProperty("index").GetInt64());
                Assert.Equal("report.pdf", annotation.GetProperty("filename").GetString());
            },
            annotation =>
            {
                Assert.Equal("file_path", annotation.GetProperty("type").GetString());
                Assert.Equal("file_2", annotation.GetProperty("file_id").GetString());
                Assert.Equal(2, annotation.GetProperty("index").GetInt64());
            },
            annotation =>
            {
                Assert.Equal("container_file_citation", annotation.GetProperty("type").GetString());
                Assert.Equal("container_1", annotation.GetProperty("container_id").GetString());
                Assert.Equal("file_3", annotation.GetProperty("file_id").GetString());
                Assert.Equal(6, annotation.GetProperty("start_index").GetInt64());
                Assert.Equal(11, annotation.GetProperty("end_index").GetInt64());
                Assert.Equal("chart.png", annotation.GetProperty("filename").GetString());
            });
    }

    private static async Task<IHost> BuildTestHostAsync(
        Action<WebApplication> configure,
        Action<WebApplicationBuilder>? configureBuilder = null)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        configureBuilder?.Invoke(builder);

        var mockAgent = new Mock<AIAgent>();
        mockAgent.SetupGet(a => a.Name).Returns("test-agent");
        builder.Services.AddFoundryResponses(mockAgent.Object);

        var app = builder.Build();
        configure(app);
        await app.StartAsync();
        return app;
    }
}
