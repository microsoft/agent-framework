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
using Moq;

namespace Microsoft.Agents.AI.Mem0.UnitTests;

/// <summary>
/// Tests for <see cref="Mem0Provider"/>.
/// </summary>
public sealed class Mem0ProviderTests : IDisposable
{
    private readonly Mock<ILogger<Mem0Provider>> _loggerMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;
    private readonly RecordingHandler _handler = new();
    private readonly HttpClient _httpClient;
    private bool _disposed;

    public Mem0ProviderTests()
    {
        this._loggerMock = new();
        this._loggerFactoryMock = new();
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(this._loggerMock.Object);
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(typeof(Mem0Provider).FullName!))
            .Returns(this._loggerMock.Object);

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
        var ex = Assert.Throws<ArgumentException>(() => new Mem0Provider(client, new Mem0ProviderScope() { ThreadId = "tid" }));
        Assert.StartsWith("The HttpClient BaseAddress must be set for Mem0 operations.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenNoStorageScopeValueIsSet()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new Mem0Provider(this._httpClient, new Mem0ProviderScope()));
        Assert.StartsWith("At least one of ApplicationId, AgentId, ThreadId, or UserId must be provided for the storage scope.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenNoSearchScopeValueIsSet()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new Mem0Provider(this._httpClient, new Mem0ProviderScope() { ThreadId = "tid" }, new Mem0ProviderScope()));
        Assert.StartsWith("At least one of ApplicationId, AgentId, ThreadId, or UserId must be provided for the search scope.", ex.Message);
    }

    [Fact]
    public void DeserializingConstructor_Throws_WithEmptyJsonElement()
    {
        // Arrange
        var jsonElement = JsonSerializer.SerializeToElement(new object(), Mem0JsonUtilities.DefaultOptions);

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => new Mem0Provider(this._httpClient, jsonElement));
        Assert.StartsWith("The Mem0Provider state did not contain the required scope properties.", ex.Message);
    }

    [Fact]
    public async Task InvokingAsync_PerformsSearch_AndReturnsContextMessageAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"session_id\": \"thread\" } ]");
        var storageScope = new Mem0ProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "thread",
            UserId = "user"
        };
        var sut = new Mem0Provider(this._httpClient, storageScope, loggerFactory: this._loggerFactoryMock.Object);
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

        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Mem0AIContextProvider: Retrieved 1 memories.")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);

        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Trace,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Mem0AIContextProvider: Search Results\nInput:What is my name?\nOutput")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task InvokedAsync_PersistsAllowedMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyOk(); // For first CreateMemory
        this._handler.EnqueueEmptyOk(); // For second CreateMemory
        this._handler.EnqueueEmptyOk(); // For third CreateMemory
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var sut = new Mem0Provider(this._httpClient, storageScope);

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
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var sut = new Mem0Provider(this._httpClient, storageScope);

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
    public async Task InvokedAsync_ShouldNotThrow_WhenStorageFailsAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var sut = new Mem0Provider(this._httpClient, storageScope, loggerFactory: this._loggerFactoryMock.Object);
        this._handler.EnqueueEmptyInternalServerError();

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
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Mem0AIContextProvider: Failed to send messages to Mem0 due to error")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task ClearStoredMemoriesAsync_SendsDeleteWithQueryAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, storageScope);
        this._handler.EnqueueEmptyOk(); // for DELETE

        // Act
        await sut.ClearStoredMemoriesAsync();

        // Assert
        var delete = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Delete);
        Assert.Equal("https://localhost/v1/memories/?app_id=app&agent_id=agent&run_id=thread&user_id=user", delete.RequestMessage.RequestUri!.AbsoluteUri);
    }

    [Fact]
    public void Serialize_RoundTripsScopes()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app", AgentId = "agent", ThreadId = "thread", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, storageScope, options: new() { ContextPrompt = "Custom:" }, loggerFactory: this._loggerFactoryMock.Object);

        // Act
        var stateElement = sut.Serialize();
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());
        var storageScopeElement = doc.RootElement.GetProperty("storageScope");
        Assert.Equal("app", storageScopeElement.GetProperty("applicationId").GetString());
        Assert.Equal("agent", storageScopeElement.GetProperty("agentId").GetString());
        Assert.Equal("thread", storageScopeElement.GetProperty("threadId").GetString());
        Assert.Equal("user", storageScopeElement.GetProperty("userId").GetString());

        var sut2 = new Mem0Provider(this._httpClient, stateElement);
        var stateElement2 = sut2.Serialize();

        // Assert
        using JsonDocument doc2 = JsonDocument.Parse(stateElement2.GetRawText());
        var storageScopeElement2 = doc2.RootElement.GetProperty("storageScope");
        Assert.Equal("app", storageScopeElement2.GetProperty("applicationId").GetString());
        Assert.Equal("agent", storageScopeElement2.GetProperty("agentId").GetString());
        Assert.Equal("thread", storageScopeElement2.GetProperty("threadId").GetString());
        Assert.Equal("user", storageScopeElement2.GetProperty("userId").GetString());
    }

    [Fact]
    public void Serialize_DoesNotIncludeDefaultContextPrompt()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app" };
        var sut = new Mem0Provider(this._httpClient, storageScope);

        // Act
        var stateElement = sut.Serialize();

        // Assert
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());
        Assert.False(doc.RootElement.TryGetProperty("contextPrompt", out _));
    }

    [Fact]
    public async Task InvokingAsync_ShouldNotThrow_WhenSearchFailsAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app" };
        var provider = new Mem0Provider(this._httpClient, storageScope, loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Null(aiContext.Messages);
        Assert.Null(aiContext.Tools);
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Mem0AIContextProvider: Failed to search Mem0 for memories due to error")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    private static bool ContainsOrdinal(string source, string value) => source.IndexOf(value, StringComparison.Ordinal) >= 0;

    public void Dispose()
    {
        if (!this._disposed)
        {
            this._httpClient.Dispose();
            this._handler.Dispose();
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

        public void EnqueueEmptyInternalServerError() => this._responses.Enqueue(new HttpResponseMessage(System.Net.HttpStatusCode.InternalServerError));
    }
}
