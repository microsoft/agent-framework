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
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

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

        this._loggerMock
            .Setup(f => f.IsEnabled(It.IsAny<LogLevel>()))
            .Returns(true);

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
        var ex = Assert.Throws<ArgumentException>(() => new Mem0Provider(client, _ => new Mem0Provider.State(new Mem0ProviderScope { ThreadId = "tid" })));
        Assert.StartsWith("The HttpClient BaseAddress must be set for Mem0 operations.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenStateInitializerIsNull()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentNullException>(() => new Mem0Provider(this._httpClient, null!));
        Assert.Contains("stateInitializer", ex.Message);
    }

    [Fact]
    public void StateKey_ReturnsDefaultKey_WhenNoOptionsProvided()
    {
        // Arrange & Act
        var provider = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(new Mem0ProviderScope { ThreadId = "tid" }));

        // Assert
        Assert.Equal("Mem0Provider", provider.StateKey);
    }

    [Fact]
    public void StateKey_ReturnsCustomKey_WhenSetViaOptions()
    {
        // Arrange & Act
        var provider = new Mem0Provider(
            this._httpClient,
            _ => new Mem0Provider.State(new Mem0ProviderScope { ThreadId = "tid" }),
            new Mem0ProviderOptions { StateKey = "custom-key" });

        // Assert
        Assert.Equal("custom-key", provider.StateKey);
    }

    [Fact]
    public async Task InvokingAsync_PerformsSearch_AndReturnsContextMessageAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"thread_id\": \"session\" } ]");
        var storageScope = new Mem0ProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "session",
            UserId = "user"
        };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: new() { EnableSensitiveTelemetryData = true }, loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "What is my name?") } });

        // Act
        var aiContext = await sut.InvokingAsync(invokingContext);

        // Assert
        var searchRequest = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Post && r.RequestMessage.RequestUri!.AbsoluteUri.EndsWith("/v1/memories/search/", StringComparison.Ordinal));
        using JsonDocument doc = JsonDocument.Parse(searchRequest.RequestBody);
        Assert.Equal("app", doc.RootElement.GetProperty("app_id").GetString());
        Assert.Equal("agent", doc.RootElement.GetProperty("agent_id").GetString());
        Assert.Equal("session", doc.RootElement.GetProperty("run_id").GetString());
        Assert.Equal("user", doc.RootElement.GetProperty("user_id").GetString());
        Assert.Equal("What is my name?", doc.RootElement.GetProperty("query").GetString());

        Assert.NotNull(aiContext.Messages);
        var messages = aiContext.Messages.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal(AgentRequestMessageSourceType.External, messages[0].GetAgentRequestMessageSourceType());
        var contextMessage = messages[1];
        Assert.Equal(ChatRole.User, contextMessage.Role);
        Assert.Contains("Name is Caoimhe", contextMessage.Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, contextMessage.GetAgentRequestMessageSourceType());

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

    [Theory]
    [InlineData(false, false, 4)]
    [InlineData(true, false, 4)]
    [InlineData(false, true, 2)]
    [InlineData(true, true, 2)]
    public async Task InvokingAsync_LogsUserIdBasedOnEnableSensitiveTelemetryDataAsync(bool enableSensitiveTelemetryData, bool requestThrows, int expectedLogInvocations)
    {
        // Arrange
        if (requestThrows)
        {
            this._handler.EnqueueEmptyInternalServerError();
        }
        else
        {
            this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"thread_id\": \"session\" } ]");
        }

        var storageScope = new Mem0ProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "session",
            UserId = "user"
        };
        var options = new Mem0ProviderOptions { EnableSensitiveTelemetryData = enableSensitiveTelemetryData };
        var mockSession = new TestAgentSession();

        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: options, loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Who am I?") } });

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

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
            Assert.Equal(enableSensitiveTelemetryData ? "user" : "<redacted>", userIdValue);

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

    [Fact]
    public async Task InvokedAsync_PersistsAllowedMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyOk(); // For first CreateMemory
        this._handler.EnqueueEmptyOk(); // For second CreateMemory
        this._handler.EnqueueEmptyOk(); // For third CreateMemory
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

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
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, responseMessages));

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
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "User text"),
            new(ChatRole.System, "System text"),
            new(ChatRole.Tool, "Tool text should be ignored")
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, new InvalidOperationException("Request Failed")));

        // Assert
        Assert.Empty(this._handler.Requests);
    }

    [Fact]
    public async Task InvokedAsync_ShouldNotThrow_WhenStorageFailsAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), loggerFactory: this._loggerFactoryMock.Object);
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
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, responseMessages));

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

    [Theory]
    [InlineData(false, false, 0)]
    [InlineData(true, false, 0)]
    [InlineData(false, true, 2)]
    [InlineData(true, true, 2)]
    public async Task InvokedAsync_LogsUserIdBasedOnEnableSensitiveTelemetryDataAsync(bool enableSensitiveTelemetryData, bool requestThrows, int expectedLogCount)
    {
        // Arrange
        if (requestThrows)
        {
            this._handler.EnqueueEmptyInternalServerError();
        }
        else
        {
            this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"thread_id\": \"session\" } ]");
        }

        var storageScope = new Mem0ProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "session",
            UserId = "user"
        };

        var options = new Mem0ProviderOptions { EnableSensitiveTelemetryData = enableSensitiveTelemetryData };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: options, loggerFactory: this._loggerFactoryMock.Object);
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "User text")
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "Assistant text")
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, responseMessages));

        // Assert
        Assert.Equal(expectedLogCount, this._loggerMock.Invocations.Count);
        foreach (var logInvocation in this._loggerMock.Invocations)
        {
            if (logInvocation.Method.Name == nameof(ILogger.IsEnabled))
            {
                continue;
            }

            var state = Assert.IsType<IReadOnlyList<KeyValuePair<string, object?>>>(logInvocation.Arguments[2], exactMatch: false);
            var userIdValue = state.First(kvp => kvp.Key == "UserId").Value;
            Assert.Equal(enableSensitiveTelemetryData ? "user" : "<redacted>", userIdValue);
        }
    }

    [Fact]
    public async Task ClearStoredMemoriesAsync_SendsDeleteWithQueryAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app", AgentId = "agent", ThreadId = "session", UserId = "user" };
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));
        this._handler.EnqueueEmptyOk(); // for DELETE
        var mockSession = new TestAgentSession();

        // Act
        await sut.ClearStoredMemoriesAsync(mockSession);

        // Assert
        var delete = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Delete);
        Assert.Equal("https://localhost/v1/memories/?app_id=app&agent_id=agent&run_id=session&user_id=user", delete.RequestMessage.RequestUri!.AbsoluteUri);
    }

    [Fact]
    public async Task InvokingAsync_ShouldNotThrow_WhenSearchFailsAsync()
    {
        // Arrange
        var storageScope = new Mem0ProviderScope { ApplicationId = "app" };
        var mockSession = new TestAgentSession();
        var provider = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        Assert.Single(aiContext.Messages);
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

    [Fact]
    public async Task StateInitializer_IsCalledOnceAndStoredInStateBagAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");
        this._handler.EnqueueJsonResponse("[]");
        var storageScope = new Mem0ProviderScope { ApplicationId = "app" };
        var mockSession = new TestAgentSession();
        int initializerCallCount = 0;
        var sut = new Mem0Provider(this._httpClient, _ =>
        {
            initializerCallCount++;
            return new Mem0Provider.State(storageScope);
        });
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal(1, initializerCallCount);
    }

    [Fact]
    public async Task StateKey_CanBeConfiguredViaOptionsAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");
        var storageScope = new Mem0ProviderScope { ApplicationId = "app" };
        var mockSession = new TestAgentSession();
        const string CustomKey = "MyCustomKey";
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: new() { StateKey = CustomKey });
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.True(mockSession.StateBag.TryGetValue<Mem0Provider.State>(CustomKey, out var state, Mem0JsonUtilities.DefaultOptions));
        Assert.NotNull(state);
    }

    [Fact]
    public async Task InvokingAsync_DefaultFilter_ExcludesNonExternalMessagesFromSearchAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]"); // Empty search results
        var storageScope = new Mem0ProviderScope { ApplicationId = "app", AgentId = "agent", ThreadId = "session", UserId = "user" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = requestMessages });

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Search query should only contain the External message
        var searchRequest = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Post);
        using JsonDocument doc = JsonDocument.Parse(searchRequest.RequestBody);
        Assert.Equal("External message", doc.RootElement.GetProperty("query").GetString());
    }

    [Fact]
    public async Task InvokingAsync_CustomSearchInputFilter_OverridesDefaultAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]"); // Empty search results
        var storageScope = new Mem0ProviderScope { ApplicationId = "app", AgentId = "agent", ThreadId = "session", UserId = "user" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: new Mem0ProviderOptions
        {
            SearchInputMessageFilter = messages => messages // No filtering
        });

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = requestMessages });

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Search query should contain all messages (custom identity filter)
        var searchRequest = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Post);
        using JsonDocument doc = JsonDocument.Parse(searchRequest.RequestBody);
        var queryText = doc.RootElement.GetProperty("query").GetString();
        Assert.Contains("External message", queryText);
        Assert.Contains("From history", queryText);
    }

    [Fact]
    public async Task InvokedAsync_DefaultFilter_ExcludesNonExternalMessagesFromStorageAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyOk(); // For the one message that should be stored
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, []));

        // Assert - Only the External message should be persisted
        var memoryPosts = this._handler.Requests.Where(r => r.RequestMessage.RequestUri!.AbsolutePath == "/v1/memories/" && r.RequestMessage.Method == HttpMethod.Post).ToList();
        Assert.Single(memoryPosts);
        Assert.Contains("External message", memoryPosts[0].RequestBody);
        Assert.DoesNotContain(memoryPosts, r => ContainsOrdinal(r.RequestBody, "From history"));
    }

    [Fact]
    public async Task InvokedAsync_CustomStorageInputFilter_OverridesDefaultAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyOk(); // For first CreateMemory
        this._handler.EnqueueEmptyOk(); // For second CreateMemory
        var storageScope = new Mem0ProviderScope { ApplicationId = "a", AgentId = "b", ThreadId = "c", UserId = "d" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope), options: new Mem0ProviderOptions
        {
            StorageInputMessageFilter = messages => messages // No filtering - store everything
        });

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, requestMessages, []));

        // Assert - Both messages should be persisted (identity filter overrides default)
        var memoryPosts = this._handler.Requests.Where(r => r.RequestMessage.RequestUri!.AbsolutePath == "/v1/memories/" && r.RequestMessage.Method == HttpMethod.Post).ToList();
        Assert.Equal(2, memoryPosts.Count);
    }

    #region MessageAIContextProvider.InvokingAsync Tests

    [Fact]
    public async Task MessageInvokingAsync_SearchesAndReturnsMergedMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[ { \"id\": \"1\", \"memory\": \"Name is Caoimhe\", \"hash\": \"h\", \"metadata\": null, \"score\": 0.9, \"created_at\": \"2023-01-01T00:00:00Z\", \"updated_at\": null, \"user_id\": \"u\", \"app_id\": null, \"agent_id\": \"agent\", \"thread_id\": \"session\" } ]");
        var storageScope = new Mem0ProviderScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            ThreadId = "session",
            UserId = "user"
        };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var inputMsg = new ChatMessage(ChatRole.User, "What is my name?");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, mockSession, [inputMsg]);

        // Act
        var messages = (await sut.InvokingAsync(context)).ToList();

        // Assert - input message + memory message, with stamping
        Assert.Equal(2, messages.Count);
        Assert.Equal("What is my name?", messages[0].Text);
        Assert.Contains("Name is Caoimhe", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task MessageInvokingAsync_NoMemories_ReturnsOnlyInputMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");
        var storageScope = new Mem0ProviderScope
        {
            UserId = "user"
        };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var inputMsg = new ChatMessage(ChatRole.User, "Hello");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, mockSession, [inputMsg]);

        // Act
        var messages = (await sut.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    [Fact]
    public async Task MessageInvokingAsync_DefaultFilter_ExcludesNonExternalMessagesAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");
        var storageScope = new Mem0ProviderScope
        {
            UserId = "user"
        };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        var externalMsg = new ChatMessage(ChatRole.User, "External question");
        var historyMsg = new ChatMessage(ChatRole.User, "History message")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, mockSession, [externalMsg, historyMsg]);

        // Act
        await sut.InvokingAsync(context);

        // Assert - Only External message used for search query
        var searchRequest = Assert.Single(this._handler.Requests, r => r.RequestMessage.Method == HttpMethod.Post && ContainsOrdinal(r.RequestMessage.RequestUri!.AbsoluteUri, "/v1/memories/search/"));
        using JsonDocument doc = JsonDocument.Parse(searchRequest.RequestBody);
        Assert.Equal("External question", doc.RootElement.GetProperty("query").GetString());
    }

    #endregion

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
        public List<(HttpRequestMessage RequestMessage, string RequestBody)> Requests { get; } = [];

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

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
            this.StateBag = new AgentSessionStateBag();
        }
    }
}
