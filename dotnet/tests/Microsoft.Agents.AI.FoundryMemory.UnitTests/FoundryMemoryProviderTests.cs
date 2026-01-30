// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.FoundryMemory.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryMemoryProvider"/>.
/// </summary>
public sealed class FoundryMemoryProviderTests
{
    private readonly Mock<IFoundryMemoryOperations> _operationsMock;
    private readonly Mock<ILogger<FoundryMemoryProvider>> _loggerMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;

    public FoundryMemoryProviderTests()
    {
        this._operationsMock = new();
        this._loggerMock = new();
        this._loggerFactoryMock = new();
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(this._loggerMock.Object);
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(typeof(FoundryMemoryProvider).FullName!))
            .Returns(this._loggerMock.Object);

        this._loggerMock
            .Setup(f => f.IsEnabled(It.IsAny<LogLevel>()))
            .Returns(true);
    }

    [Fact]
    public void Constructor_Throws_WhenOperationsIsNull()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            (IFoundryMemoryOperations)null!,
            new FoundryMemoryProviderScope { Scope = "test" },
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.Equal("operations", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenScopeIsNull()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            this._operationsMock.Object,
            null!,
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.Equal("scope", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenScopeValueIsEmpty()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            this._operationsMock.Object,
            new FoundryMemoryProviderScope(),
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.StartsWith("The Scope property must be provided.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsMissing()
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            this._operationsMock.Object,
            new FoundryMemoryProviderScope { Scope = "test" },
            new FoundryMemoryProviderOptions()));
        Assert.StartsWith("The MemoryStoreName option must be provided.", ex.Message);
    }

    [Fact]
    public void DeserializingConstructor_Throws_WithEmptyJsonElement()
    {
        // Arrange
        JsonElement jsonElement = JsonSerializer.SerializeToElement(new object(), FoundryMemoryJsonUtilities.DefaultOptions);

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => new FoundryMemoryProvider(
            this._operationsMock.Object,
            jsonElement,
            options: new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.StartsWith("The FoundryMemoryProvider state did not contain the required scope property.", ex.Message);
    }

    [Fact]
    public async Task InvokingAsync_PerformsSearch_AndReturnsContextMessageAsync()
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.SearchMemoriesAsync(
                "my-store",
                "user-123",
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                5,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(["User prefers dark roast coffee", "User is from Seattle"]);

        FoundryMemoryProviderScope scope = new() { Scope = "user-123" };
        FoundryMemoryProviderOptions options = new()
        {
            MemoryStoreName = "my-store",
            EnableSensitiveTelemetryData = true
        };

        FoundryMemoryProvider sut = new(this._operationsMock.Object, scope, options);
        AIContextProvider.InvokingContext invokingContext = new([new ChatMessage(ChatRole.User, "What are my coffee preferences?")]);

        // Act
        AIContext aiContext = await sut.InvokingAsync(invokingContext);

        // Assert
        this._operationsMock.Verify(
            o => o.SearchMemoriesAsync("my-store", "user-123", It.IsAny<IEnumerable<MemoryInputMessage>>(), 5, It.IsAny<CancellationToken>()),
            Times.Once);

        Assert.NotNull(aiContext.Messages);
        ChatMessage contextMessage = Assert.Single(aiContext.Messages);
        Assert.Equal(ChatRole.User, contextMessage.Role);
        Assert.Contains("User prefers dark roast coffee", contextMessage.Text);
        Assert.Contains("User is from Seattle", contextMessage.Text);
    }

    [Fact]
    public async Task InvokingAsync_ReturnsEmptyContext_WhenNoMemoriesFoundAsync()
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.SearchMemoriesAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<string>());

        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });
        AIContextProvider.InvokingContext invokingContext = new([new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        AIContext aiContext = await sut.InvokingAsync(invokingContext);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage contextMessage = Assert.Single(aiContext.Messages);
        Assert.True(string.IsNullOrEmpty(contextMessage.Text)); // Text is null or empty when no memories found
    }

    [Fact]
    public async Task InvokingAsync_ShouldNotThrow_WhenSearchFailsAsync()
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.SearchMemoriesAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Search failed"));

        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" }, this._loggerFactoryMock.Object);
        AIContextProvider.InvokingContext invokingContext = new([new ChatMessage(ChatRole.User, "Q?")]);

        // Act
        AIContext aiContext = await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Null(aiContext.Messages);
        Assert.Null(aiContext.Tools);
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("FoundryMemoryProvider: Failed to search for memories due to error")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task InvokedAsync_PersistsAllowedMessagesAsync()
    {
        // Arrange
        IEnumerable<MemoryInputMessage>? capturedMessages = null;
        this._operationsMock
            .Setup(o => o.UpdateMemoriesAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string, IEnumerable<MemoryInputMessage>, int, CancellationToken>((_, _, msgs, _, _) => capturedMessages = msgs)
            .Returns(Task.CompletedTask);

        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        List<ChatMessage> requestMessages =
        [
            new(ChatRole.User, "User text"),
            new(ChatRole.System, "System text"),
            new(ChatRole.Tool, "Tool text should be ignored")
        ];
        List<ChatMessage> responseMessages = [new(ChatRole.Assistant, "Assistant text")];

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null) { ResponseMessages = responseMessages });

        // Assert
        this._operationsMock.Verify(
            o => o.UpdateMemoriesAsync("my-store", "user-123", It.IsAny<IEnumerable<MemoryInputMessage>>(), 0, It.IsAny<CancellationToken>()),
            Times.Once);

        Assert.NotNull(capturedMessages);
        List<MemoryInputMessage> messagesList = [.. capturedMessages];
        Assert.Equal(3, messagesList.Count); // user, system, assistant (tool excluded)
        Assert.Contains(messagesList, m => m.Role == "user" && m.Content == "User text");
        Assert.Contains(messagesList, m => m.Role == "system" && m.Content == "System text");
        Assert.Contains(messagesList, m => m.Role == "assistant" && m.Content == "Assistant text");
        Assert.DoesNotContain(messagesList, m => m.Content == "Tool text should be ignored");
    }

    [Fact]
    public async Task InvokedAsync_PersistsNothingForFailedRequestAsync()
    {
        // Arrange
        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        List<ChatMessage> requestMessages =
        [
            new(ChatRole.User, "User text"),
            new(ChatRole.System, "System text")
        ];

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null)
        {
            ResponseMessages = null,
            InvokeException = new InvalidOperationException("Request Failed")
        });

        // Assert
        this._operationsMock.Verify(
            o => o.UpdateMemoriesAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<IEnumerable<MemoryInputMessage>>(), It.IsAny<int>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task InvokedAsync_ShouldNotThrow_WhenStorageFailsAsync()
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.UpdateMemoriesAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Storage failed"));

        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" }, this._loggerFactoryMock.Object);

        List<ChatMessage> requestMessages = [new(ChatRole.User, "User text")];
        List<ChatMessage> responseMessages = [new(ChatRole.Assistant, "Assistant text")];

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null) { ResponseMessages = responseMessages });

        // Assert
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("FoundryMemoryProvider: Failed to send messages to update memories due to error")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task EnsureStoredMemoriesDeletedAsync_SendsDeleteRequestAsync()
    {
        // Arrange
        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Act
        await sut.EnsureStoredMemoriesDeletedAsync();

        // Assert
        this._operationsMock.Verify(
            o => o.DeleteScopeAsync("my-store", "user-123", It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task EnsureStoredMemoriesDeletedAsync_Handles404GracefullyAsync()
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.DeleteScopeAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ClientResultException(new MockPipelineResponse(404)));

        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Act & Assert - should not throw
        await sut.EnsureStoredMemoriesDeletedAsync();
    }

    [Fact]
    public void Serialize_RoundTripsScope()
    {
        // Arrange
        FoundryMemoryProviderScope scope = new() { Scope = "user-456" };
        FoundryMemoryProvider sut = new(this._operationsMock.Object, scope, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Act
        JsonElement stateElement = sut.Serialize();
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());

        // Assert (JSON uses camelCase naming policy)
        Assert.True(doc.RootElement.TryGetProperty("scope", out JsonElement scopeElement));
        Assert.Equal("user-456", scopeElement.GetProperty("scope").GetString());
    }

    [Theory]
    [InlineData(true, "user-123")]
    [InlineData(false, "<redacted>")]
    public async Task InvokingAsync_LogsScopeBasedOnEnableSensitiveTelemetryDataAsync(bool enableSensitiveTelemetryData, string expectedScopeInLog)
    {
        // Arrange
        this._operationsMock
            .Setup(o => o.SearchMemoriesAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<IEnumerable<MemoryInputMessage>>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(["test memory"]);

        FoundryMemoryProviderOptions options = new()
        {
            MemoryStoreName = "my-store",
            EnableSensitiveTelemetryData = enableSensitiveTelemetryData
        };
        FoundryMemoryProvider sut = new(this._operationsMock.Object, new FoundryMemoryProviderScope { Scope = "user-123" }, options, this._loggerFactoryMock.Object);

        AIContextProvider.InvokingContext invokingContext = new([new ChatMessage(ChatRole.User, "test")]);

        // Act
        await sut.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) =>
                    v.ToString()!.Contains("Retrieved 1 memories") &&
                    v.ToString()!.Contains($"Scope: '{expectedScopeInLog}'")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    private sealed class MockPipelineResponse : PipelineResponse
    {
        private readonly int _status;
        private readonly MockPipelineResponseHeaders _headers;

        public MockPipelineResponse(int status)
        {
            this._status = status;
            this.Content = BinaryData.Empty;
            this._headers = new MockPipelineResponseHeaders();
        }

        public override int Status => this._status;

        public override string ReasonPhrase => this._status == 404 ? "Not Found" : "OK";

        public override Stream? ContentStream
        {
            get => null;
            set { }
        }

        public override BinaryData Content { get; }

        protected override PipelineResponseHeaders HeadersCore => this._headers;

        public override BinaryData BufferContent(CancellationToken cancellationToken = default) => this.Content;

        public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default) =>
            new(this.Content);

        public override void Dispose()
        {
        }

        private sealed class MockPipelineResponseHeaders : PipelineResponseHeaders
        {
            private readonly Dictionary<string, string> _headers = new(StringComparer.OrdinalIgnoreCase);

            public override bool TryGetValue(string name, out string? value)
            {
                return this._headers.TryGetValue(name, out value);
            }

            public override bool TryGetValues(string name, out IEnumerable<string>? values)
            {
                if (this._headers.TryGetValue(name, out string? value))
                {
                    values = [value];
                    return true;
                }

                values = null;
                return false;
            }

            public override IEnumerator<KeyValuePair<string, string>> GetEnumerator()
            {
                return this._headers.GetEnumerator();
            }
        }
    }
}
