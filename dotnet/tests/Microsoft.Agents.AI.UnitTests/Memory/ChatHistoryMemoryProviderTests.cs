// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

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

        this._loggerMock
            .Setup(f => f.IsEnabled(It.IsAny<LogLevel>()))
            .Returns(true);

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
    public void StateKey_ReturnsDefaultKey_WhenNoOptionsProvided()
    {
        // Arrange & Act
        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }));

        // Assert
        Assert.Equal("ChatHistoryMemoryProvider", provider.StateKey);
    }

    [Fact]
    public void StateKey_ReturnsCustomKey_WhenSetViaOptions()
    {
        // Arrange & Act
        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            new ChatHistoryMemoryProviderOptions { StateKey = "custom-key" });

        // Assert
        Assert.Equal("custom-key", provider.StateKey);
    }

    [Fact]
    public void Constructor_Throws_ForNullVectorStore()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(
            null!,
            "testcollection",
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" })));
    }

    [Fact]
    public void Constructor_Throws_ForNullCollectionName()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            null!,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" })));
    }

    [Fact]
    public void Constructor_Throws_ForNullStateInitializer()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            "testcollection",
            1,
            null!));
    }

    [Fact]
    public void Constructor_Throws_ForInvalidVectorDimensions()
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            "testcollection",
            0,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" })));
        Assert.Throws<ArgumentOutOfRangeException>(() => new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            "testcollection",
            -5,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" })));
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
            SessionId = "session1",
            UserId = "user1"
        };

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(storeScope));

        var requestMsgWithValues = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1", AuthorName = "user1", CreatedAt = new DateTimeOffset(new DateTime(2000, 1, 1), TimeSpan.Zero) };
        var requestMsgWithNulls = new ChatMessage(ChatRole.User, "request text nulls");
        var responseMsg = new ChatMessage(ChatRole.Assistant, "response text") { MessageId = "resp-1", AuthorName = "assistant" };

        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), [requestMsgWithValues, requestMsgWithNulls], [responseMsg]);

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
        Assert.Equal("session1", stored[0]["SessionId"]);
        Assert.Equal("user1", stored[0]["UserId"]);

        Assert.Null(stored[1]["MessageId"]);
        Assert.Equal("request text nulls", stored[1]["Content"]);
        Assert.Null(stored[1]["AuthorName"]);
        Assert.Equal(ChatRole.User.ToString(), stored[1]["Role"]);
        Assert.Equal("app1", stored[1]["ApplicationId"]);
        Assert.Equal("agent1", stored[1]["AgentId"]);
        Assert.Equal("session1", stored[1]["SessionId"]);
        Assert.Equal("user1", stored[1]["UserId"]);

        Assert.Equal("resp-1", stored[2]["MessageId"]);
        Assert.Equal("response text", stored[2]["Content"]);
        Assert.Equal("assistant", stored[2]["AuthorName"]);
        Assert.Equal(ChatRole.Assistant.ToString(), stored[2]["Role"]);
        Assert.Equal("app1", stored[2]["ApplicationId"]);
        Assert.Equal("agent1", stored[2]["AgentId"]);
        Assert.Equal("session1", stored[2]["SessionId"]);
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
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }));
        var requestMsg = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1" };
        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), [requestMsg], new InvalidOperationException("Invoke failed"));

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
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            loggerFactory: this._loggerFactoryMock.Object);
        var requestMsg = new ChatMessage(ChatRole.User, "request text") { MessageId = "req-1" };
        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), [requestMsg], []);

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
    [InlineData(false, true, 2)]
    [InlineData(true, true, 2)]
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
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "user1" }),
            options: options,
            loggerFactory: this._loggerFactoryMock.Object);

        var requestMsg = new ChatMessage(ChatRole.User, "request text");
        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), [requestMsg], []);

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert
        Assert.Equal(expectedLogInvocations, this._loggerMock.Invocations.Count);
        foreach (var logInvocation in this._loggerMock.Invocations)
        {
            if (logInvocation.Method.Name == nameof(ILogger.IsEnabled))
            {
                continue;
            }

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
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: providerOptions);

        var requestMsg = new ChatMessage(ChatRole.User, "requesting relevant history");
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { requestMsg } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        this._vectorStoreCollectionMock.Verify(
            c => c.SearchAsync(
                It.Is<string>(s => s == "requesting relevant history"),
                2,
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()),
            Times.Once);

        Assert.NotNull(aiContext.Messages);
        var messages = aiContext.Messages.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal(AgentRequestMessageSourceType.External, messages[0].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
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
            SessionId = "session1",
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
                const string ExpectedFilter = "x => ((((x.ApplicationId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).applicationId) AndAlso (x.AgentId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).agentId)) AndAlso (x.UserId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).userId)) AndAlso (x.SessionId == value(Microsoft.Agents.AI.VectorDataMemory.ChatHistoryMemoryProvider+<>c__DisplayClass20_0).sessionId))";
                Assert.Equal(ExpectedFilter, options.Filter!.ToString());
            })
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(searchScope, searchScope),
            options: providerOptions);

        var requestMsg = new ChatMessage(ChatRole.User, "requesting relevant history");
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { requestMsg } });

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
    [InlineData(false, false, 2)]
    [InlineData(true, false, 2)]
    [InlineData(false, true, 2)]
    [InlineData(true, true, 2)]
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
            _ => new ChatHistoryMemoryProvider.State(scope, scope),
            options: options,
            loggerFactory: this._loggerFactoryMock.Object);

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "requesting relevant history") } });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal(expectedLogInvocations, this._loggerMock.Invocations.Count);
        foreach (var logInvocation in this._loggerMock.Invocations)
        {
            if (logInvocation.Method.Name == nameof(ILogger.IsEnabled))
            {
                continue;
            }

            var state = Assert.IsType<IReadOnlyList<KeyValuePair<string, object?>>>(logInvocation.Arguments[2], exactMatch: false);
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

    #region Message Filter Tests

    [Fact]
    public async Task InvokingAsync_DefaultFilter_ExcludesNonExternalMessagesFromSearchAsync()
    {
        // Arrange
        var providerOptions = new ChatHistoryMemoryProviderOptions
        {
            SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke,
        };

        string? capturedQuery = null;
        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, int, VectorSearchOptions<Dictionary<string, object?>>, CancellationToken>((query, _, _, _) => capturedQuery = query)
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: providerOptions);

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = requestMessages });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Only External message used for search query
        Assert.Equal("External message", capturedQuery);
    }

    [Fact]
    public async Task InvokingAsync_CustomSearchInputFilter_OverridesDefaultAsync()
    {
        // Arrange
        var providerOptions = new ChatHistoryMemoryProviderOptions
        {
            SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke,
            SearchInputMessageFilter = messages => messages // No filtering
        };

        string? capturedQuery = null;
        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, int, VectorSearchOptions<Dictionary<string, object?>>, CancellationToken>((query, _, _, _) => capturedQuery = query)
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: providerOptions);

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = requestMessages });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Both messages should be included in search query (identity filter)
        Assert.NotNull(capturedQuery);
        Assert.Contains("External message", capturedQuery);
        Assert.Contains("From history", capturedQuery);
    }

    [Fact]
    public async Task InvokedAsync_DefaultFilter_ExcludesNonExternalMessagesFromStorageAsync()
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

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }));

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), requestMessages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert - Only External message + response stored (ChatHistory and AIContextProvider excluded by default)
        Assert.Equal(2, stored.Count);
        Assert.Equal("External message", stored[0]["Content"]);
        Assert.Equal("Response", stored[1]["Content"]);
    }

    [Fact]
    public async Task InvokedAsync_CustomStorageInputFilter_OverridesDefaultAsync()
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

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: new ChatHistoryMemoryProviderOptions
            {
                StorageInputMessageFilter = messages => messages // No filtering - store everything
            });

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        var invokedContext = new AIContextProvider.InvokedContext(s_mockAgent, new TestAgentSession(), requestMessages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(invokedContext, CancellationToken.None);

        // Assert - All messages stored (identity filter overrides default)
        Assert.Equal(3, stored.Count);
        Assert.Equal("External message", stored[0]["Content"]);
        Assert.Equal("From history", stored[1]["Content"]);
        Assert.Equal("Response", stored[2]["Content"]);
    }

    #endregion

    #region MessageAIContextProvider.InvokingAsync Tests

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_SearchesAndReturnsMergedMessagesAsync()
    {
        // Arrange
        var storedItems = new List<VectorSearchResult<Dictionary<string, object?>>>
        {
            new(
                new Dictionary<string, object?>
                {
                    ["MessageId"] = "msg-1",
                    ["Content"] = "Previous message",
                    ["Role"] = ChatRole.User.ToString(),
                    ["CreatedAt"] = "2023-01-01T00:00:00.0000000+00:00"
                },
                0.9f)
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
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: new ChatHistoryMemoryProviderOptions
            {
                SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke
            });

        var inputMsg = new ChatMessage(ChatRole.User, "What was discussed?");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [inputMsg]);

        // Act
        var messages = (await provider.InvokingAsync(context)).ToList();

        // Assert - input message + search result message, with stamping
        Assert.Equal(2, messages.Count);
        Assert.Equal("What was discussed?", messages[0].Text);
        Assert.Contains("Previous message", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task MessageInvokingAsync_OnDemand_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: new ChatHistoryMemoryProviderOptions
            {
                SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling
            });

        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [new ChatMessage(ChatRole.User, "Q?")]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => provider.InvokingAsync(context).AsTask());
    }

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_NoResults_ReturnsOnlyInputMessagesAsync()
    {
        // Arrange
        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: new ChatHistoryMemoryProviderOptions
            {
                SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke
            });

        var inputMsg = new ChatMessage(ChatRole.User, "Hello");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [inputMsg]);

        // Act
        var messages = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_DefaultFilter_ExcludesNonExternalMessagesAsync()
    {
        // Arrange
        string? capturedQuery = null;
        this._vectorStoreCollectionMock
            .Setup(c => c.SearchAsync(
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<VectorSearchOptions<Dictionary<string, object?>>>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, int, VectorSearchOptions<Dictionary<string, object?>>, CancellationToken>((query, _, _, _) => capturedQuery = query)
            .Returns(ToAsyncEnumerableAsync(new List<VectorSearchResult<Dictionary<string, object?>>>()));

        var provider = new ChatHistoryMemoryProvider(
            this._vectorStoreMock.Object,
            TestCollectionName,
            1,
            _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "UID" }),
            options: new ChatHistoryMemoryProviderOptions
            {
                SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke
            });

        var externalMsg = new ChatMessage(ChatRole.User, "External message");
        var historyMsg = new ChatMessage(ChatRole.System, "From history")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [externalMsg, historyMsg]);

        // Act
        await provider.InvokingAsync(context);

        // Assert - Only External message used for search query
        Assert.Equal("External message", capturedQuery);
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

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
        }

        public TestAgentSession(AgentSessionStateBag stateBag)
        {
            this.StateBag = stateBag;
        }
    }
}
