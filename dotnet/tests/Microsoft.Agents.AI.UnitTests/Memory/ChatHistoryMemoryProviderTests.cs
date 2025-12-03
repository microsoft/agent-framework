// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.VectorData;
using Moq;

namespace Microsoft.Agents.AI.Memory.UnitTests;

/// <summary>
/// Contains unit tests for the <see cref="ChatHistoryMemoryProvider"/> class.
/// </summary>
public class ChatHistoryMemoryProviderTests
{
    private readonly Mock<ILogger<ChatHistoryMemoryProvider>> _loggerMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;

    private readonly Mock<VectorStore> _vectorStoreMock;
    private readonly Mock<VectorStoreCollection<object, Dictionary<string, object?>>> _vectorStoreCollectionMock;
    private const string TestCollectionName = "testcollection";

    public ChatHistoryMemoryProviderTests()
    {
        this._loggerMock = new();
        this._loggerFactoryMock = new();
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(this._loggerMock.Object);
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(typeof(ChatHistoryMemoryProvider).FullName!))
            .Returns(this._loggerMock.Object);

        this._vectorStoreCollectionMock = new(MockBehavior.Strict);
        this._vectorStoreMock = new(MockBehavior.Strict);

        this._vectorStoreCollectionMock
            .Setup(c => c.EnsureCollectionExistsAsync(It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        this._vectorStoreMock
            .Setup(vs => vs.GetDynamicCollection(
                It.IsAny<string>(),
                It.IsAny<VectorStoreCollectionDefinition>()))
            .Returns(this._vectorStoreCollectionMock.Object);
    }

    [Fact]
    public void Constructor_Throws_ForNullVectorStore()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(null!, "testcollection", 1, new ChatHistoryMemoryProviderScope() { UserId = "UID" }));
    }

    [Fact]
    public void Constructor_Throws_ForNullCollectionName()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, null!, 1, new ChatHistoryMemoryProviderScope() { UserId = "UID" }));
    }

    [Fact]
    public void Constructor_Throws_ForNullStorageScope()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, "testcollection", 1, null!));
    }

    [Fact]
    public void Constructor_Throws_ForInvalidVectorDimensions()
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, "testcollection", 0, new ChatHistoryMemoryProviderScope() { UserId = "UID" }));
        Assert.Throws<ArgumentOutOfRangeException>(() => new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, "testcollection", -5, new ChatHistoryMemoryProviderScope() { UserId = "UID" }));
    }

    #region InvokedAsync Tests

    [Fact]
    public async Task InvokedAsync_UpsertsMessages_ToCollectionAsync()
    {
        // Arrange
        var stored = new List<Dictionary<string, object?>>();

        this._vectorStoreCollectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<Dictionary<string, object?>>, CancellationToken>((items, ct) =>
            {
                if (items != null)
                {
                    stored.AddRange(items);
                }
            })
            .Returns(Task.CompletedTask);

        var storeScope = new ChatHistoryMemoryProviderScope
        {
            ApplicationId = "app1",
            AgentId = "agent1",
            ThreadId = "thread1",
            UserId = "user1"
        };

        var provider = new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, TestCollectionName, 1, storeScope);

        var requestMsgWithValues = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1", AuthorName = "user1", CreatedAt = new DateTimeOffset(new DateTime(2000, 1, 1), TimeSpan.Zero) };
        var requestMsgWithNulls = new ChatMessage(ChatRole.User, "request text nulls");
        var responseMsg = new ChatMessage(ChatRole.Assistant, "response text") { MessageId = "resp-1", AuthorName = "assistant" };

        var invokedContext = new AIContextProvider.InvokedContext([requestMsgWithValues, requestMsgWithNulls], aiContextProviderMessages: null)
        {
            ResponseMessages = [responseMsg]
        };

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert
        this._vectorStoreCollectionMock.Verify(
            m => m.EnsureCollectionExistsAsync(It.IsAny<CancellationToken>()),
            Times.Once);

        Assert.Equal(3, stored.Count);

        Assert.Equal("req-1", stored[0]["MessageId"]);
        Assert.Equal("request text", stored[0]["Content"]);
        Assert.Equal("user1", stored[0]["AuthorName"]);
        Assert.Equal(ChatRole.User.ToString(), stored[0]["Role"]);
        Assert.Equal("2000-01-01T00:00:00.0000000+00:00", stored[0]["CreatedAt"]);
        Assert.Equal("app1", stored[0]["ApplicationId"]);
        Assert.Equal("agent1", stored[0]["AgentId"]);
        Assert.Equal("thread1", stored[0]["ThreadId"]);
        Assert.Equal("user1", stored[0]["UserId"]);

        Assert.Null(stored[1]["MessageId"]);
        Assert.Equal("request text nulls", stored[1]["Content"]);
        Assert.Null(stored[1]["AuthorName"]);
        Assert.Equal(ChatRole.User.ToString(), stored[1]["Role"]);
        Assert.Equal("app1", stored[1]["ApplicationId"]);
        Assert.Equal("agent1", stored[1]["AgentId"]);
        Assert.Equal("thread1", stored[1]["ThreadId"]);
        Assert.Equal("user1", stored[1]["UserId"]);

        Assert.Equal("resp-1", stored[2]["MessageId"]);
        Assert.Equal("response text", stored[2]["Content"]);
        Assert.Equal("assistant", stored[2]["AuthorName"]);
        Assert.Equal(ChatRole.Assistant.ToString(), stored[2]["Role"]);
        Assert.Equal("app1", stored[2]["ApplicationId"]);
        Assert.Equal("agent1", stored[2]["AgentId"]);
        Assert.Equal("thread1", stored[2]["ThreadId"]);
        Assert.Equal("user1", stored[2]["UserId"]);
    }

    [Fact]
    public async Task InvokedAsync_DoesNotUpsertMessages_WhenInvokeFailedAsync()
    {
        // Arrange
        this._vectorStoreCollectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            new ChatHistoryMemoryProviderScope() { UserId = "UID" });
        var requestMsg = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1" };
        var invokedContext = new AIContextProvider.InvokedContext([requestMsg], aiContextProviderMessages: null)
        {
            InvokeException = new InvalidOperationException("Invoke failed")
        };

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert
        this._vectorStoreCollectionMock.Verify(
            c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task InvokedAsync_DoesNotThrow_WhenUpsertThrowsAsync()
    {
        // Arrange
        this._vectorStoreCollectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Upsert failed"));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            new ChatHistoryMemoryProviderScope() { UserId = "UID" },
            loggerFactory: this._loggerFactoryMock.Object);
        var requestMsg = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1" };
        var invokedContext = new AIContextProvider.InvokedContext([requestMsg], aiContextProviderMessages: null);

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("ChatHistoryMemoryProvider: Failed to add messages to chat history vector store due to error")),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Theory]
    [InlineData(false, false, 0)]
    [InlineData(true, false, 0)]
    [InlineData(false, true, 1)]
    [InlineData(true, true, 1)]
    public async Task InvokedAsync_LogsUserIdBasedOnEnableSensitiveTelemetryDataAsync(bool enableSensitiveTelemetryData, bool requestThrows, int expectedLogInvocations)
    {
        // Arrange
        var options = new ChatHistoryMemoryProviderOptions
        {
            EnableSensitiveTelemetryData = enableSensitiveTelemetryData
        };

        if (requestThrows)
        {
            this._vectorStoreCollectionMock
                .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
                .ThrowsAsync(new InvalidOperationException("Upsert failed"));
        }
        else
        {
            this._vectorStoreCollectionMock
                .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
                .Returns(Task.CompletedTask);
        }

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            new ChatHistoryMemoryProviderScope { UserId = "user1" },
            options: options,
            loggerFactory: this._loggerFactoryMock.Object);

        var requestMsg = new ChatMessage(ChatRole.User, "request text");
        var invokedContext = new AIContextProvider.InvokedContext([requestMsg], aiContextProviderMessages: null);

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert
        Assert.Equal(expectedLogInvocations, this._loggerMock.Invocations.Count);
        foreach (var logInvocation in this._loggerMock.Invocations)
        {
            var state = Assert.IsType<IReadOnlyList<KeyValuePair<string, object?>>>(logInvocation.Arguments[2], exactMatch: false);
            var userIdValue = state.First(kvp => kvp.Key == "UserId").Value;
            Assert.Equal(enableSensitiveTelemetryData ? "user1" : "<redacted>", userIdValue);
        }
    }

    #endregion

    #region InvokingAsync Tests

    [Fact]
    public async Task InvokedAsync_SearchesVectorStoreAsync()
    {
        // Arrange
        var providerOptions = new ChatHistoryMemoryProviderOptions
        {
            SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke,
            MaxResults = 2,
            ContextPrompt = "Here is the relevant chat history:\n"
        };

        var storedItems = new List<VectorSearchResult<Dictionary<string, object?>>>
        {
            new(
                new Dictionary<string, object?>
                {
                    ["MessageId"] = "msg-1",
                    ["Content"] = "First stored message",
                    ["Role"] = ChatRole.User.ToString(),
                    ["CreatedAt"] = "2023-01-01T00:00:00.0000000+00:00"
                },
                0.9f),
            new(
                new Dictionary<string, object?>
                {
                    ["MessageId"] = "msg-2",
                    ["Content"] = "Second stored message",
                    ["Role"] = ChatRole.User.ToString(),
                    ["CreatedAt"] = "2023-01-02T00:00:00.0000000+00:00"
                },
                0.8f)
        };

        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(storedItems));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            new ChatHistoryMemoryProviderScope() { UserId = "UID" },
            options: providerOptions);

        var requestMsg = new ChatMessage(ChatRole.User, "requesting relevant history");
        var invokingContext = new AIContextProvider.InvokingContext([requestMsg]);

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        this._vectorStoreCollectionMock.Verify(
            c => c.SearchAsync(
                It.Is<string>(s => s == "requesting relevant history"),
                2,
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task InvokedAsync_CreatesFilter_WhenSearchScopeProvidedAsync()
    {
        // Arrange
        var providerOptions = new ChatHistoryMemoryProviderOptions
        {
            SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke,
            MaxResults = 2,
            ContextPrompt = "Here is the relevant chat history:\n"
        };

        var searchScope = new ChatHistoryMemoryProviderScope
        {
            ApplicationId = "app1",
            AgentId = "agent1",
            ThreadId = "thread1",
            UserId = "user1"
        };

        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Callback((string query, int maxResults, VectorSearchOptions<Dictionary<string, object?>> options, CancellationToken ct) =>
            {
                // Verify that the filter was created correctly
                const string ExpectedFilter = "x => ((((x.ApplicationId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).applicationId) AndAlso (x.AgentId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).agentId)) AndAlso (x.UserId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).userId)) AndAlso (x.ThreadId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).threadId))";
                Assert.Equal(ExpectedFilter, options.Filter!.ToString());
            })
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, TestCollectionName, 1, options: providerOptions, storageScope: searchScope, searchScope: searchScope);

        var requestMsg = new ChatMessage(ChatRole.User, "requesting relevant history");
        var invokingContext = new AIContextProvider.InvokingContext([requestMsg]);

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        this._vectorStoreCollectionMock.Verify(
            c => c.SearchAsync(
                It.Is<string>(s => s == "requesting relevant history"),
                2,
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Theory]
    [InlineData(false, false, 1)]
    [InlineData(true, false, 1)]
    [InlineData(false, true, 1)]
    [InlineData(true, true, 1)]
    public async Task InvokingAsync_LogsUserIdBasedOnEnableSensitiveTelemetryDataAsync(bool enableSensitiveTelemetryData, bool requestThrows, int expectedLogInvocations)
    {
        // Arrange
        var options = new ChatHistoryMemoryProviderOptions
        {
            SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke,
            EnableSensitiveTelemetryData = enableSensitiveTelemetryData
        };

        var scope = new ChatHistoryMemoryProviderScope
        {
            UserId = "user1"
        };

        if (requestThrows)
        {
            this._vectorStoreCollectionMock
                .Setup(c => c.SearchAsync(
                    It.IsAny<string>(),
                    It.IsAny<int>(),
                    It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                    It.IsAny<CancellationToken>()))
                .Throws(new InvalidOperationException("Search failed"));
        }
        else
        {
            this._vectorStoreCollectionMock
                .Setup(c => c.SearchAsync(
                    It.IsAny<string>(),
                    It.IsAny<int>(),
                    It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                    It.IsAny<CancellationToken>()))
                .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));
        }

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            storageScope: scope,
            searchScope: scope,
            options: options,
            loggerFactory: this._loggerFactoryMock.Object);

        var invokingContext = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "requesting relevant history")]);

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal(expectedLogInvocations, this._loggerMock.Invocations.Count);
        foreach (var logInvocation in this._loggerMock.Invocations)
        {
            var state = Assert.IsAssignableFrom<IReadOnlyList<KeyValuePair<string, object?>>>(logInvocation.Arguments[2]);
            var userIdValue = state.First(kvp => kvp.Key == "UserId").Value;
            Assert.Equal(enableSensitiveTelemetryData ? "user1" : "<redacted>", userIdValue);

            var inputValue = state.FirstOrDefault(kvp => kvp.Key == "Input").Value;
            if (inputValue != null)
            {
                Assert.Equal(enableSensitiveTelemetryData ? "Who am I?" : "<redacted>", inputValue);
            }

            var messageTextValue = state.FirstOrDefault(kvp => kvp.Key == "MessageText").Value;
            if (messageTextValue != null)
            {
                Assert.Equal(enableSensitiveTelemetryData ? "## Memories\nConsider the following memories when answering user questions:\nName is Caoimhe" : "<redacted>", messageTextValue);
            }
        }
    }

    #endregion

    #region Serialization Tests

    [Fact]
    public void Serialize_Deserialize_RoundtripsScopes()
    {
        // Arrange
        var storageScope = new ChatHistoryMemoryProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "thread",
            UserId = "user"
        };

        var searchScope = new ChatHistoryMemoryProviderScope
        {
            ApplicationId = "app2",
            AgentId = "agent2",
            ThreadId = "thread2",
            UserId = "user2"
        };

        var provider = new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, TestCollectionName, 1, storageScope: storageScope, searchScope: searchScope);

        // Act
        var stateElement = provider.Serialize();

        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());
        var storage = doc.RootElement.GetProperty("storageScope");
        Assert.Equal("app", storage.GetProperty("applicationId").GetString());
        Assert.Equal("agent", storage.GetProperty("agentId").GetString());
        Assert.Equal("thread", storage.GetProperty("threadId").GetString());
        Assert.Equal("user", storage.GetProperty("userId").GetString());

        var search = doc.RootElement.GetProperty("searchScope");
        Assert.Equal("app2", search.GetProperty("applicationId").GetString());
        Assert.Equal("agent2", search.GetProperty("agentId").GetString());
        Assert.Equal("thread2", search.GetProperty("threadId").GetString());
        Assert.Equal("user2", search.GetProperty("userId").GetString());

        // Act - deserialize and serialize again
        var provider2 = new ChatHistoryMemoryProvider(this._vectorStoreMock.Object, TestCollectionName, 1, serializedState: stateElement);
        var stateElement2 = provider2.Serialize();

        // Assert - roundtrip the state
        Assert.Equal(stateElement.GetRawText(), stateElement2.GetRawText());
    }

    #endregion

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var update in values)
        {
            yield return update;
        }
    }
}
