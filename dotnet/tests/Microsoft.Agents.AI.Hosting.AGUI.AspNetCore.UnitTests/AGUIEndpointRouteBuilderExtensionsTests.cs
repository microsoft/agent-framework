// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIEndpointRouteBuilderExtensions"/> class.
/// </summary>
public sealed class AGUIEndpointRouteBuilderExtensionsTests
{
    [Fact]
    public void MapAGUIAgent_MapsEndpoint_AtSpecifiedPattern()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        const string Pattern = "/api/agent";
        AIAgent agent = new TestAgent();

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUI(Pattern, agent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task MapAGUIAgent_WithNullOrInvalidInput_Returns400BadRequestAsync()
    {
        // Arrange
        DefaultHttpContext context = new();
        context.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes("invalid json"));
        context.RequestAborted = CancellationToken.None;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, ctx, props) => new TestAgent());

        // Act
        await handler(context);

        // Assert
        Assert.Equal(StatusCodes.Status400BadRequest, context.Response.StatusCode);
    }

    [Fact]
    public async Task MapAGUIAgent_InvokesAgentFactory_WithCorrectMessagesAndContextAsync()
    {
        // Arrange
        List<ChatMessage>? capturedMessages = null;
        IEnumerable<KeyValuePair<string, string>>? capturedContext = null;

        AIAgent factory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props)
        {
            capturedMessages = messages.ToList();
            capturedContext = context;
            return new TestAgent();
        }

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }],
            Context = [new AGUIContextItem { Description = "key1", Value = "value1" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate(factory);

        // Act
        await handler(httpContext);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Single(capturedMessages);
        Assert.Equal("Test", capturedMessages[0].Text);
        Assert.NotNull(capturedContext);
        Assert.Contains(capturedContext, kvp => kvp.Key == "key1" && kvp.Value == "value1");
    }

    [Fact]
    public async Task MapAGUIAgent_ReturnsSSEResponseStream_WithCorrectContentTypeAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        Assert.Equal("text/event-stream", httpContext.Response.ContentType);
    }

    [Fact]
    public async Task MapAGUIAgent_PassesCancellationToken_ToAgentExecutionAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        cts.Cancel();

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();
        httpContext.RequestAborted = cts.Token;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => handler(httpContext));
    }

    [Fact]
    public async Task MapAGUIAgent_ConvertsInputMessages_ToChatMessagesBeforeFactoryAsync()
    {
        // Arrange
        List<ChatMessage>? capturedMessages = null;

        AIAgent factory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props)
        {
            capturedMessages = messages.ToList();
            return new TestAgent();
        }

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages =
            [
                new AGUIUserMessage { Id = "m1", Content = "First" },
                new AGUIAssistantMessage { Id = "m2", Content = "Second" }
            ]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate(factory);

        // Act
        await handler(httpContext);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
        Assert.Equal("First", capturedMessages[0].Text);
        Assert.Equal(ChatRole.Assistant, capturedMessages[1].Role);
        Assert.Equal("Second", capturedMessages[1].Text);
    }

    [Fact]
    public async Task MapAGUIAgent_ProducesValidAGUIEventStream_WithRunStartAndFinishAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        responseStream.Position = 0;
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());

        List<JsonElement> events = ParseSseEvents(responseContent);

        JsonElement runStarted = Assert.Single(events, static e => e.GetProperty("type").GetString() == AGUIEventTypes.RunStarted);
        JsonElement runFinished = Assert.Single(events, static e => e.GetProperty("type").GetString() == AGUIEventTypes.RunFinished);

        Assert.Equal("thread1", runStarted.GetProperty("threadId").GetString());
        Assert.Equal("run1", runStarted.GetProperty("runId").GetString());
        Assert.Equal("thread1", runFinished.GetProperty("threadId").GetString());
        Assert.Equal("run1", runFinished.GetProperty("runId").GetString());
    }

    [Fact]
    public async Task MapAGUIAgent_ProducesTextMessageEvents_InCorrectOrderAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Hello" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        responseStream.Position = 0;
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());

        List<JsonElement> events = ParseSseEvents(responseContent);
        List<string?> eventTypes = new(events.Count);
        foreach (JsonElement evt in events)
        {
            eventTypes.Add(evt.GetProperty("type").GetString());
        }

        Assert.Contains(AGUIEventTypes.RunStarted, eventTypes);
        Assert.Contains(AGUIEventTypes.TextMessageContent, eventTypes);
        Assert.Contains(AGUIEventTypes.RunFinished, eventTypes);

        int runStartIndex = eventTypes.IndexOf(AGUIEventTypes.RunStarted);
        int firstContentIndex = eventTypes.IndexOf(AGUIEventTypes.TextMessageContent);
        int runFinishIndex = eventTypes.LastIndexOf(AGUIEventTypes.RunFinished);

        Assert.True(runStartIndex < firstContentIndex, "Run start should precede text content.");
        Assert.True(firstContentIndex < runFinishIndex, "Text content should precede run finish.");
    }

    [Fact]
    public async Task MapAGUIAgent_EmitsTextMessageContent_WithCorrectDeltaAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        responseStream.Position = 0;
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());

        List<JsonElement> events = ParseSseEvents(responseContent);
        JsonElement textContentEvent = Assert.Single(events, static e => e.GetProperty("type").GetString() == AGUIEventTypes.TextMessageContent);

        Assert.Equal("Test response", textContentEvent.GetProperty("delta").GetString());
    }

    [Fact]
    public async Task MapAGUIAgent_WithCustomAgent_ProducesExpectedStreamStructureAsync()
    {
        // Arrange
        static AIAgent CustomAgentFactory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props)
        {
            return new MultiResponseAgent();
        }

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "custom_thread",
            RunId = "custom_run",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Multi" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        RequestDelegate handler = this.CreateRequestDelegate(CustomAgentFactory);

        // Act
        await handler(httpContext);

        // Assert
        responseStream.Position = 0;
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());

        List<JsonElement> events = ParseSseEvents(responseContent);
        List<JsonElement> contentEvents = [];
        foreach (JsonElement evt in events)
        {
            if (evt.GetProperty("type").GetString() == AGUIEventTypes.TextMessageContent)
            {
                contentEvents.Add(evt);
            }
        }

        Assert.True(contentEvents.Count >= 3, $"Expected at least 3 text_message.content events, got {contentEvents.Count}");

        List<string?> deltas = new(contentEvents.Count);
        foreach (JsonElement contentEvent in contentEvents)
        {
            deltas.Add(contentEvent.GetProperty("delta").GetString());
        }

        Assert.Contains("First", deltas);
        Assert.Contains(" part", deltas);
        Assert.Contains(" of response", deltas);
    }

    [Fact]
    public async Task MapAGUIAgent_ProducesCorrectSessionAndRunIds_InAllEventsAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "test_thread_123",
            RunId = "test_run_456",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        responseStream.Position = 0;
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());

        List<JsonElement> events = ParseSseEvents(responseContent);
        JsonElement runStarted = Assert.Single(events, static e => e.GetProperty("type").GetString() == AGUIEventTypes.RunStarted);

        Assert.Equal("test_thread_123", runStarted.GetProperty("threadId").GetString());
        Assert.Equal("test_run_456", runStarted.GetProperty("runId").GetString());
    }

    [Fact]
    public async Task MapAGUIAgent_WithProxiedResultResolver_EmitsOnlyRunStartedAndRunFinishedAsync()
    {
        // Arrange
        const string ThreadId = "proxy-thread";
        const string RunId = "proxy-run";
        int resolverCalls = 0;
        int agentCalls = 0;

        await using TestServerHost host = await TestServerHost.CreateAsync(
            new CountingAgent(() => agentCalls++),
            async (forwardedProperties, cancellationToken) =>
            {
                resolverCalls++;
                Assert.Equal(JsonValueKind.Object, forwardedProperties.ValueKind);
                Assert.Equal("resources/read", forwardedProperties.GetProperty("__proxiedMCPRequest").GetProperty("method").GetString());
                await Task.CompletedTask.ConfigureAwait(false);
                using JsonDocument document = JsonDocument.Parse("""
                    {
                      "contents": [
                        {
                          "uri": "ui://get-time.html",
                          "mimeType": "text/html;profile=mcp-app",
                          "text": "<html></html>"
                        }
                      ]
                    }
                    """);
                return document.RootElement.Clone();
            });

        using StringContent content = new(BuildRequestJson(ThreadId, RunId, forwardedPropsJson: """
            {
              "__proxiedMCPRequest": {
                "method": "resources/read",
                "params": { "uri": "ui://get-time.html" }
              }
            }
            """), Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await host.Client.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        string responseContent = await response.Content.ReadAsStringAsync();

        // Assert
        List<JsonElement> events = ParseSseEvents(responseContent);
        Assert.Equal(1, resolverCalls);
        Assert.Equal(0, agentCalls);
        Assert.Collection(
            events,
            evt =>
            {
                Assert.Equal(AGUIEventTypes.RunStarted, evt.GetProperty("type").GetString());
                Assert.Equal(ThreadId, evt.GetProperty("threadId").GetString());
                Assert.Equal(RunId, evt.GetProperty("runId").GetString());
            },
            evt =>
            {
                Assert.Equal(AGUIEventTypes.RunFinished, evt.GetProperty("type").GetString());
                Assert.Equal(ThreadId, evt.GetProperty("threadId").GetString());
                Assert.Equal(RunId, evt.GetProperty("runId").GetString());
                JsonElement result = evt.GetProperty("result");
                JsonElement contents = result.GetProperty("contents");
                Assert.Single(contents.EnumerateArray());
                JsonElement firstContent = contents[0];
                Assert.Equal("ui://get-time.html", firstContent.GetProperty("uri").GetString());
            });
    }

    [Fact]
    public async Task MapAGUIAgent_WithEmptyForwardedProperties_DoesNotInvokeProxiedResultResolverAsync()
    {
        // Arrange
        int resolverCalls = 0;
        int agentCalls = 0;

        await using TestServerHost host = await TestServerHost.CreateAsync(
            new CountingAgent(() => agentCalls++),
            (forwardedProperties, cancellationToken) =>
            {
                resolverCalls++;
                return ValueTask.FromResult<JsonElement?>(null);
            });

        using StringContent content = new(BuildRequestJson("thread1", "run1", forwardedPropsJson: "{}"), Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await host.Client.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        string responseContent = await response.Content.ReadAsStringAsync();

        // Assert
        List<JsonElement> events = ParseSseEvents(responseContent);
        Assert.Equal(0, resolverCalls);
        Assert.Equal(1, agentCalls);
        Assert.Contains(events, static evt => evt.GetProperty("type").GetString() == AGUIEventTypes.TextMessageContent);
    }

    [Fact]
    public async Task MapAGUIAgent_WithoutForwardedProperties_DoesNotInvokeProxiedResultResolverAsync()
    {
        // Arrange
        int resolverCalls = 0;
        int agentCalls = 0;

        await using TestServerHost host = await TestServerHost.CreateAsync(
            new CountingAgent(() => agentCalls++),
            (forwardedProperties, cancellationToken) =>
            {
                resolverCalls++;
                return ValueTask.FromResult<JsonElement?>(null);
            });

        using StringContent content = new(BuildRequestJson("thread1", "run1"), Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await host.Client.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        string responseContent = await response.Content.ReadAsStringAsync();

        // Assert
        List<JsonElement> events = ParseSseEvents(responseContent);
        Assert.Equal(0, resolverCalls);
        Assert.Equal(1, agentCalls);
        Assert.Contains(events, static evt => evt.GetProperty("type").GetString() == AGUIEventTypes.RunFinished);
    }

    [Fact]
    public async Task MapAGUIAgent_WhenProxiedResultResolverReturnsNull_FallsBackToAgentAsync()
    {
        // Arrange
        int resolverCalls = 0;
        int agentCalls = 0;

        await using TestServerHost host = await TestServerHost.CreateAsync(
            new CountingAgent(() => agentCalls++),
            (forwardedProperties, cancellationToken) =>
            {
                resolverCalls++;
                return ValueTask.FromResult<JsonElement?>(null);
            });

        using StringContent content = new(BuildRequestJson("thread1", "run1", forwardedPropsJson: """
            {
              "customProp": "value"
            }
            """), Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await host.Client.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        string responseContent = await response.Content.ReadAsStringAsync();

        // Assert
        List<JsonElement> events = ParseSseEvents(responseContent);
        Assert.Equal(1, resolverCalls);
        Assert.Equal(1, agentCalls);
        Assert.Contains(events, static evt => evt.GetProperty("type").GetString() == AGUIEventTypes.TextMessageContent);
    }

    private static List<JsonElement> ParseSseEvents(string responseContent)
    {
        List<JsonElement> events = [];
        using StringReader reader = new(responseContent);
        StringBuilder dataBuilder = new();
        string? line;

        while ((line = reader.ReadLine()) != null)
        {
            if (line.StartsWith("data:", StringComparison.Ordinal))
            {
                string payload = line.Length > 5 && line[5] == ' '
                    ? line.Substring(6)
                    : line.Substring(5);
                dataBuilder.Append(payload);
            }
            else if (line.Length == 0 && dataBuilder.Length > 0)
            {
                using JsonDocument document = JsonDocument.Parse(dataBuilder.ToString());
                events.Add(document.RootElement.Clone());
                dataBuilder.Clear();
            }
        }

        if (dataBuilder.Length > 0)
        {
            using JsonDocument document = JsonDocument.Parse(dataBuilder.ToString());
            events.Add(document.RootElement.Clone());
        }

        return events;
    }

    private static string BuildRequestJson(string threadId, string runId, string? forwardedPropsJson = null)
    {
        forwardedPropsJson ??= null;

        return $$"""
            {
              "threadId": "{{threadId}}",
              "runId": "{{runId}}",
              "messages": [{ "id": "m1", "role": "user", "content": "Test" }]{{(forwardedPropsJson is null ? string.Empty : ",\n              \"forwardedProps\": " + forwardedPropsJson)}}
            }
            """;
    }

    private sealed class MultiResponseAgent : AIAgent
    {
        protected override string? IdCore => "multi-response-agent";

        public override string? Description => "Agent that produces multiple text chunks";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(serializedState.Deserialize<TestAgentSession>(jsonSerializerOptions)!);

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            if (session is not TestAgentSession testSession)
            {
                throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(TestAgentSession)}' can be serialized by this agent.");
            }

            return new(JsonSerializer.SerializeToElement(testSession, jsonSerializerOptions));
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield return new AgentResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "First"));
            yield return new AgentResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, " part"));
            yield return new AgentResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, " of response"));
        }
    }

    private sealed class CountingAgent(Action onRunStreaming) : AIAgent
    {
        protected override string? IdCore => "counting-agent";

        public override string? Description => "Agent that counts streaming invocations";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(serializedState.Deserialize<TestAgentSession>(jsonSerializerOptions)!);

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            if (session is not TestAgentSession testSession)
            {
                throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(TestAgentSession)}' can be serialized by this agent.");
            }

            return new(JsonSerializer.SerializeToElement(testSession, jsonSerializerOptions));
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            onRunStreaming();
            await Task.CompletedTask;
            yield return new AgentResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Test response"));
        }
    }

    private sealed class TestServerHost : IAsyncDisposable
    {
        private readonly WebApplication _app;

        private TestServerHost(WebApplication app, HttpClient client)
        {
            this._app = app;
            this.Client = client;
        }

        public HttpClient Client { get; }

        public static async Task<TestServerHost> CreateAsync(AIAgent agent, AGUIEndpointRouteBuilderExtensions.ProxiedResultResolver? proxiedResultResolver = null)
        {
            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.Services.AddAGUI();
            builder.WebHost.UseTestServer();

            WebApplication app = builder.Build();
            if (proxiedResultResolver is null)
            {
                app.MapAGUI("/agent", agent);
            }
            else
            {
                app.MapAGUI("/agent", agent, proxiedResultResolver);
            }

            await app.StartAsync().ConfigureAwait(false);

            TestServer testServer = app.Services.GetRequiredService<IServer>() as TestServer
                ?? throw new InvalidOperationException("TestServer not found");

            return new TestServerHost(app, testServer.CreateClient());
        }

        public async ValueTask DisposeAsync()
        {
            this.Client.Dispose();
            await this._app.DisposeAsync().ConfigureAwait(false);
        }
    }

    private RequestDelegate CreateRequestDelegate(
        Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> factory)
    {
        return async context =>
        {
            CancellationToken cancellationToken = context.RequestAborted;

            RunAgentInput? input;
            try
            {
                input = await JsonSerializer.DeserializeAsync(
                    context.Request.Body,
                    AGUIJsonSerializerContext.Default.RunAgentInput,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (JsonException)
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }

            if (input is null)
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }

            IEnumerable<ChatMessage> messages = input.Messages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);
            IEnumerable<KeyValuePair<string, string>> contextValues = input.Context.Select(c => new KeyValuePair<string, string>(c.Description, c.Value));
            JsonElement forwardedProps = input.ForwardedProperties;
            AIAgent agent = factory(messages, [], contextValues, forwardedProps);

            IAsyncEnumerable<BaseEvent> events = agent.RunStreamingAsync(
                messages,
                cancellationToken: cancellationToken)
                .AsChatResponseUpdatesAsync()
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    AGUIJsonSerializerContext.Default.Options,
                    cancellationToken);

            ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
            await new AGUIServerSentEventsResult(events, logger).ExecuteAsync(context).ConfigureAwait(false);
        };
    }

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
        }

        [JsonConstructor]
        public TestAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }

    private sealed class TestAgent : AIAgent
    {
        protected override string? IdCore => "test-agent";

        public override string? Description => "Test agent";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(serializedState.Deserialize<TestAgentSession>(jsonSerializerOptions)!);

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            if (session is not TestAgentSession testSession)
            {
                throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(TestAgentSession)}' can be serialized by this agent.");
            }

            return new(JsonSerializer.SerializeToElement(testSession, jsonSerializerOptions));
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield return new AgentResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Test response"));
        }
    }
}
