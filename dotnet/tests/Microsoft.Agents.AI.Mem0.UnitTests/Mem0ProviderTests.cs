// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Mem0.UnitTests;

/// <summary>
/// Tests for <see cref="Mem0Provider"/>.
/// </summary>
public sealed class Mem0ProviderTests : IDisposable
{
    private readonly RecordingHandler _handler = new();
    private readonly HttpClient _httpClient;
    private readonly ILoggerFactory _loggerFactory = LoggerFactory.Create(b => b.AddProvider(new NullLoggerProvider()));
    private bool _disposed;

    public Mem0ProviderTests()
    {
        this._httpClient = new HttpClient(this._handler)
        {
            BaseAddress = new Uri("https://localhost/")
        };
    }

    [Fact]
    public void Constructor_Throws_WhenBaseAddressMissing()
    {
        // Arrange
        using HttpClient client = new();

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new Mem0Provider(client));
        Assert.StartsWith("The HttpClient BaseAddress must be set for Mem0 operations.", ex.Message);
    }

    [Fact]
    public void Constructor_Defaults_Scopes()
    {
        // Arrange & Act
        var sut = new Mem0Provider(this._httpClient);

        // Assert
        Assert.Null(sut.ApplicationId);
        Assert.Null(sut.AgentId);
        Assert.Null(sut.ThreadId);
        Assert.Null(sut.UserId);
    }

    [Fact]
    public void DeserializingConstructor_Defaults_Scopes()
    {
        // Arrange & Act
        var jsonElement = JsonSerializer.SerializeToElement(new object(), Mem0JsonUtilities.DefaultOptions);
        var sut = new Mem0Provider(this._httpClient, jsonElement);

        // Assert
        Assert.Null(sut.ApplicationId);
        Assert.Null(sut.AgentId);
        Assert.Null(sut.ThreadId);
        Assert.Null(sut.UserId);
    }

    [Fact]
    public async Task InvokingAsync_PerformsSearch_AndReturnsContextMessageAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"session_id\": \"thread\" } ]");
        var options = new Mem0ProviderOptions
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "thread",
            UserId = "user"
        };
        var sut = new Mem0Provider(this._httpClient, options, this._loggerFactory);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "What is my name?") });

        // Act
        var aiContext = await sut.InvokingAsync(invokingContext);

        // Assert
        var searchRequest = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Post && r.RequestMessage.RequestUri!.AbsoluteUri.EndsWith("/v1/memories/search/", StringComparison.Ordinal));
        using JsonDocument doc = JsonDocument.Parse(searchRequest.RequestBody);
        Assert.Equal("app", doc.RootElement.GetProperty("app_id").GetString());
        Assert.Equal("agent", doc.RootElement.GetProperty("agent_id").GetString());
        Assert.Equal("thread", doc.RootElement.GetProperty("run_id").GetString());
        Assert.Equal("user", doc.RootElement.GetProperty("user_id").GetString());
        Assert.Equal("What is my name?", doc.RootElement.GetProperty("query").GetString());

        Assert.NotNull(aiContext.Messages);
        var contextMessage = Assert.Single(aiContext.Messages);
        Assert.Equal(ChatRole.User, contextMessage.Role);
        Assert.Contains("Name is Caoimhe", contextMessage.Text);
    }

    [Fact]
    public async Task InvokedAsync_PersistsAllowedMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyOk(); // For first CreateMemory
        this._handler.EnqueueEmptyOk(); // For second CreateMemory
        this._handler.EnqueueEmptyOk(); // For third CreateMemory
        var options = new Mem0ProviderOptions { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var sut = new Mem0Provider(this._httpClient, options);

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "User text"),
            new(ChatRole.System, "System text"),
            new(ChatRole.Tool, "Tool text should be ignored")
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "Assistant text")
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null) { ResponseMessages = responseMessages });

        // Assert
        var memoryPosts = this._handler.Requests.Where(r => r.RequestMessage.RequestUri!.AbsolutePath == "/v1/memories/" && r.RequestMessage.Method == HttpMethod.Post).ToList();
        Assert.Equal(3, memoryPosts.Count); // user, system, assistant
        foreach (var req in memoryPosts)
        {
            Assert.Contains("\"messages\":[{", req.RequestBody);
        }
        Assert.DoesNotContain(memoryPosts, r => ContainsOrdinal(r.RequestBody, "Tool text"));
    }

    [Fact]
    public async Task InvokedAsync_PersistsNothingForFailedRequestAsync()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var sut = new Mem0Provider(this._httpClient, options);

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "User text"),
            new(ChatRole.System, "System text"),
            new(ChatRole.Tool, "Tool text should be ignored")
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null) { ResponseMessages = null, InvokeException = new InvalidOperationException("Request Failed") });

        // Assert
        Assert.Empty(this._handler.Requests);
    }

    [Fact]
    public async Task ClearStoredMemoriesAsync_SendsDeleteWithQueryAsync()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, options);
        this._handler.EnqueueEmptyOk(); // for DELETE

        // Act
        await sut.ClearStoredMemoriesAsync();

        // Assert
        var delete = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Delete);
        Assert.Equal("https://localhost/v1/memories/?app_id=app&agent_id=agent&run_id=thread&user_id=user", delete.RequestMessage.RequestUri!.AbsoluteUri);
    }

    [Fact]
    public void Properties_Roundtrip()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, options);

        // Assert
        Assert.Equal("app", sut.ApplicationId);
        Assert.Equal("agent", sut.AgentId);
        Assert.Equal("thread", sut.ThreadId);
        Assert.Equal("user", sut.UserId);

        // Act
        sut.ApplicationId = "app2";
        sut.AgentId = "agent2";
        sut.ThreadId = "thread2";
        sut.UserId = "user2";

        // Assert
        Assert.Equal("app2", sut.ApplicationId);
        Assert.Equal("agent2", sut.AgentId);
        Assert.Equal("thread2", sut.ThreadId);
        Assert.Equal("user2", sut.UserId);
    }

    [Fact]
    public void Serialize_Deserialize_Roundtrips()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, options);

        // Act
        var stateElement = sut.Serialize();
        var sut2 = new Mem0Provider(this._httpClient, stateElement);

        // Assert
        Assert.Equal("app", sut.ApplicationId);
        Assert.Equal("agent", sut.AgentId);
        Assert.Equal("thread", sut.ThreadId);
        Assert.Equal("user", sut.UserId);

        Assert.Equal("app", sut2.ApplicationId);
        Assert.Equal("agent", sut2.AgentId);
        Assert.Equal("thread", sut2.ThreadId);
        Assert.Equal("user", sut2.UserId);
    }

    [Fact]
    public void Serialize_RoundTripsCustomContextPrompt()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user", ContextPrompt = "Custom:" };
        var sut = new Mem0Provider(this._httpClient, options);

        // Act
        var stateElement = sut.Serialize();
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());
        Assert.Equal("Custom:", doc.RootElement.GetProperty("contextPrompt").GetString());

        var sut2 = new Mem0Provider(this._httpClient, stateElement);
        var stateElement2 = sut2.Serialize();

        // Assert
        using JsonDocument doc2 = JsonDocument.Parse(stateElement2.GetRawText());
        Assert.Equal("Custom:", doc2.RootElement.GetProperty("contextPrompt").GetString());
    }

    [Fact]
    public void Serialize_DoesNotIncludeDefaultContextPrompt()
    {
        // Arrange
        var options = new Mem0ProviderOptions { ApplicationId = "app" };
        var sut = new Mem0Provider(this._httpClient, options);

        // Act
        var stateElement = sut.Serialize();

        // Assert
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());
        Assert.False(doc.RootElement.TryGetProperty("contextPrompt", out _));
    }

    [Fact]
    public async Task InvokingAsync_Throws_WhenNoScopesAsync()
    {
        // Arrange
        var sut = new Mem0Provider(this._httpClient, new Mem0ProviderOptions());
        var ctx = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Test") });

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => sut.InvokingAsync(ctx).AsTask());
    }

    private static bool ContainsOrdinal(string source, string value) => source.IndexOf(value, StringComparison.Ordinal) >= 0;

    public void Dispose()
    {
        if (!this._disposed)
        {
            this._httpClient.Dispose();
            this._handler.Dispose();
            this._loggerFactory.Dispose();
            this._disposed = true;
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Queue<HttpResponseMessage> _responses = new();
        public List<(HttpRequestMessage RequestMessage, string RequestBody)> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
#if NET
            var requestBody = await (request.Content?.ReadAsStringAsync(cancellationToken) ?? Task.FromResult(string.Empty));
#else
            var requestBody = await (request.Content?.ReadAsStringAsync() ?? Task.FromResult(string.Empty));
#endif
            this.Requests.Add((request, requestBody));
            if (this._responses.Count > 0)
            {
                return this._responses.Dequeue();
            }
            return new HttpResponseMessage(System.Net.HttpStatusCode.OK);
        }

        public void EnqueueJsonResponse(string json)
        {
            this._responses.Enqueue(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent(json, System.Text.Encoding.UTF8, "application/json")
            });
        }

        public void EnqueueEmptyOk() => this._responses.Enqueue(new HttpResponseMessage(System.Net.HttpStatusCode.OK));
    }

    private sealed class NullLoggerProvider : ILoggerProvider
    {
        public ILogger CreateLogger(string categoryName) => new NullLogger();
        public void Dispose() { }

        private sealed class NullLogger : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
            public bool IsEnabled(LogLevel logLevel) => false;
            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) { }
        }
    }
}
