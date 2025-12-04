// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Net.Http;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

public sealed class ForwardedPropertiesTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task ForwardedProps_AreParsedAndPassedToAgent_WhenProvidedInRequestAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        // Create request JSON with forwardedProps (per AG-UI protocol spec)
        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test forwarded props" }],
                "forwardedProps": { "customProp": "customValue", "sessionId": "test-session-123" }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.ValueKind.Should().Be(JsonValueKind.Object);
        fakeAgent.ReceivedForwardedProperties.GetProperty("customProp").GetString().Should().Be("customValue");
        fakeAgent.ReceivedForwardedProperties.GetProperty("sessionId").GetString().Should().Be("test-session-123");
    }

    [Fact]
    public async Task ForwardedProps_WithNestedObjects_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test nested props" }],
                "forwardedProps": {
                    "user": { "id": "user-1", "name": "Test User" },
                    "metadata": { "version": "1.0", "feature": "test" }
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.ValueKind.Should().Be(JsonValueKind.Object);

        JsonElement user = fakeAgent.ReceivedForwardedProperties.GetProperty("user");
        user.GetProperty("id").GetString().Should().Be("user-1");
        user.GetProperty("name").GetString().Should().Be("Test User");

        JsonElement metadata = fakeAgent.ReceivedForwardedProperties.GetProperty("metadata");
        metadata.GetProperty("version").GetString().Should().Be("1.0");
        metadata.GetProperty("feature").GetString().Should().Be("test");
    }

    [Fact]
    public async Task ForwardedProps_WithArrays_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test array props" }],
                "forwardedProps": {
                    "tags": ["tag1", "tag2", "tag3"],
                    "scores": [1, 2, 3, 4, 5]
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.ValueKind.Should().Be(JsonValueKind.Object);

        JsonElement tags = fakeAgent.ReceivedForwardedProperties.GetProperty("tags");
        tags.GetArrayLength().Should().Be(3);
        tags[0].GetString().Should().Be("tag1");

        JsonElement scores = fakeAgent.ReceivedForwardedProperties.GetProperty("scores");
        scores.GetArrayLength().Should().Be(5);
        scores[2].GetInt32().Should().Be(3);
    }

    [Fact]
    public async Task ForwardedProps_WhenEmpty_DoesNotCauseErrorsAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test empty props" }],
                "forwardedProps": {}
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
    }

    [Fact]
    public async Task ForwardedProps_WhenNotProvided_AgentStillWorksAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test no props" }]
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.ValueKind.Should().Be(JsonValueKind.Undefined);
    }

    [Fact]
    public async Task ForwardedProps_ReturnsValidSSEResponse_WithTextDeltaEventsAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test response" }],
                "forwardedProps": { "customProp": "value" }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();

        Stream stream = await response.Content.ReadAsStreamAsync();
        List<SseItem<string>> events = [];
        await foreach (SseItem<string> item in SseParser.Create(stream).EnumerateAsync())
        {
            events.Add(item);
        }

        // Assert
        events.Should().NotBeEmpty();

        // SSE events have EventType = "message" and the actual type is in the JSON data
        // Should have run_started event
        events.Should().Contain(e => e.Data != null && e.Data.Contains("\"type\":\"RUN_STARTED\""));

        // Should have text_message_start event
        events.Should().Contain(e => e.Data != null && e.Data.Contains("\"type\":\"TEXT_MESSAGE_START\""));

        // Should have text_message_content event with the response text
        events.Should().Contain(e => e.Data != null && e.Data.Contains("\"type\":\"TEXT_MESSAGE_CONTENT\""));

        // Should have run_finished event
        events.Should().Contain(e => e.Data != null && e.Data.Contains("\"type\":\"RUN_FINISHED\""));
    }

    [Fact]
    public async Task ForwardedProps_WithMixedTypes_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "thread-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test mixed types" }],
                "forwardedProps": {
                    "stringProp": "text",
                    "numberProp": 42,
                    "boolProp": true,
                    "nullProp": null,
                    "arrayProp": [1, "two", false],
                    "objectProp": { "nested": "value" }
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        response.IsSuccessStatusCode.Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.ValueKind.Should().Be(JsonValueKind.Object);

        fakeAgent.ReceivedForwardedProperties.GetProperty("stringProp").GetString().Should().Be("text");
        fakeAgent.ReceivedForwardedProperties.GetProperty("numberProp").GetInt32().Should().Be(42);
        fakeAgent.ReceivedForwardedProperties.GetProperty("boolProp").GetBoolean().Should().BeTrue();
        fakeAgent.ReceivedForwardedProperties.GetProperty("nullProp").ValueKind.Should().Be(JsonValueKind.Null);
        fakeAgent.ReceivedForwardedProperties.GetProperty("arrayProp").GetArrayLength().Should().Be(3);
        fakeAgent.ReceivedForwardedProperties.GetProperty("objectProp").GetProperty("nested").GetString().Should().Be("value");
    }

    private async Task SetupTestServerAsync(FakeForwardedPropsAgent fakeAgent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUI();
        builder.WebHost.UseTestServer();

        this._app = builder.Build();

        this._app.MapAGUI("/agent", fakeAgent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }
}

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated in tests")]
internal sealed class FakeForwardedPropsAgent : AIAgent
{
    public FakeForwardedPropsAgent()
    {
    }

    public override string? Description => "Agent for forwarded properties testing";

    public JsonElement ReceivedForwardedProperties { get; private set; }

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this.RunStreamingAsync(messages, thread, options, cancellationToken).ToAgentRunResponseAsync(cancellationToken);
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Extract forwarded properties from ChatOptions.AdditionalProperties (set by AG-UI hosting layer)
        if (options is ChatClientAgentRunOptions { ChatOptions.AdditionalProperties: { } properties } &&
            properties.TryGetValue("ag_ui_forwarded_properties", out object? propsObj) &&
            propsObj is JsonElement forwardedProps)
        {
            this.ReceivedForwardedProperties = forwardedProps;
        }

        // Always return a text response
        string messageId = Guid.NewGuid().ToString("N");
        yield return new AgentRunResponseUpdate
        {
            MessageId = messageId,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Forwarded props processed")]
        };

        await Task.CompletedTask;
    }

    public override AgentThread GetNewThread() => new FakeInMemoryAgentThread();

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new FakeInMemoryAgentThread(serializedThread, jsonSerializerOptions);
    }

    private sealed class FakeInMemoryAgentThread : InMemoryAgentThread
    {
        public FakeInMemoryAgentThread()
            : base()
        {
        }

        public FakeInMemoryAgentThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            : base(serializedThread, jsonSerializerOptions)
        {
        }
    }

    public override object? GetService(Type serviceType, object? serviceKey = null) => null;
}
