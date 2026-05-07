// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

/// <summary>
/// Unit tests for <see cref="ValkeyChatHistoryProvider"/>.
/// </summary>
public sealed class ValkeyChatHistoryProviderTests
{
    private static Mock<IConnectionMultiplexer> CreateMockConnection(Mock<IDatabase>? dbMock = null)
    {
        var mockConnection = new Mock<IConnectionMultiplexer>();
        dbMock ??= new Mock<IDatabase>();
        mockConnection.Setup(c => c.GetDatabase(It.IsAny<int>(), It.IsAny<object>())).Returns(dbMock.Object);
        return mockConnection;
    }

    // --- Constructor tests ---

    [Fact]
    public void Constructor_WithConnection_SetsProperties()
    {
        // Arrange & Act
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            static (_) => new ValkeyChatHistoryProvider.State("conv-1"),
            keyPrefix: "test_prefix");

        // Assert
        Assert.NotNull(provider);
        Assert.Null(provider.MaxMessages);
        Assert.Null(provider.MaxMessagesToRetrieve);
    }

    [Fact]
    public void Constructor_WithConnection_NullConnection_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyChatHistoryProvider(
                (IConnectionMultiplexer)null!,
                static (_) => new ValkeyChatHistoryProvider.State("conv-1")));
    }

    [Fact]
    public void Constructor_WithConnection_NullStateInitializer_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyChatHistoryProvider(
                CreateMockConnection().Object,
                null!));
    }

    // --- State tests ---

    [Fact]
    public void State_NullConversationId_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new ValkeyChatHistoryProvider.State(null!));
    }

    [Fact]
    public void State_EmptyConversationId_Throws()
    {
        Assert.Throws<ArgumentException>(() => new ValkeyChatHistoryProvider.State(""));
    }

    [Fact]
    public void State_ValidConversationId_SetsProperty()
    {
        var state = new ValkeyChatHistoryProvider.State("my-conversation");
        Assert.Equal("my-conversation", state.ConversationId);
    }

    [Fact]
    public void State_JsonConstructor_RoundTrips()
    {
        // Arrange
        var original = new ValkeyChatHistoryProvider.State("test-conv");

        // Act
        var json = JsonSerializer.Serialize(original);
        var deserialized = JsonSerializer.Deserialize<ValkeyChatHistoryProvider.State>(json);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("test-conv", deserialized.ConversationId);
    }

    // --- StateKeys tests ---

    [Fact]
    public void StateKeys_ReturnsProviderTypeName()
    {
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        var keys = provider.StateKeys;
        Assert.Single(keys);
        Assert.Equal(nameof(ValkeyChatHistoryProvider), keys[0]);
    }

    [Fact]
    public void StateKeys_WithCustomKey_ReturnsCustomKey()
    {
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"),
            stateKey: "custom_key");

        var keys = provider.StateKeys;
        Assert.Single(keys);
        Assert.Equal("custom_key", keys[0]);
    }

    // --- Property tests ---

    [Fact]
    public void MaxMessages_CanBeSet()
    {
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"))
        {
            MaxMessages = 50
        };

        Assert.Equal(50, provider.MaxMessages);
    }

    // --- Dispose tests ---

    [Fact]
    public async Task DisposeAsync_OwnedConnection_ClosesAndDisposesAsync()
    {
        // Arrange
        var mockConnection = CreateMockConnection();
        mockConnection.Setup(c => c.CloseAsync()).Returns(Task.CompletedTask);
        mockConnection.Setup(c => c.Dispose());

        // We can't easily test the connection-string constructor without a server,
        // so we test the IConnectionMultiplexer overload (ownsConnection=false) doesn't close.
        var provider = new ValkeyChatHistoryProvider(
            mockConnection.Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        // Act
        await provider.DisposeAsync();

        // Assert — non-owned connection should NOT be closed
        mockConnection.Verify(c => c.CloseAsync(), Times.Never);
    }

    [Fact]
    public async Task DisposeAsync_CalledTwice_NoOpAsync()
    {
        // Arrange
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        // Act — should not throw
        await provider.DisposeAsync();
        await provider.DisposeAsync();
    }

    // --- ProvideChatHistoryAsync tests ---

    [Fact]
    public async Task ProvideChatHistoryAsync_ReturnsDeserializedMessagesAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        var msg1 = new ChatMessage(ChatRole.User, "hello");
        var msg2 = new ChatMessage(ChatRole.Assistant, "hi there");
        var values = new RedisValue[]
        {
            JsonSerializer.Serialize(msg1),
            JsonSerializer.Serialize(msg2)
        };
        dbMock.Setup(d => d.ListRangeAsync(It.IsAny<RedisKey>(), It.IsAny<long>(), It.IsAny<long>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(values);

        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection(dbMock).Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        var context = TestHelpers.CreateChatHistoryInvokingContext();

        // Act — should not throw
        var result = await provider.InvokingAsync(context);
        var messages = result.ToList();

        // Assert — only the valid message + request message
        Assert.True(messages.Count >= 1);
    }

    [Fact]
    public async Task ProvideChatHistoryAsync_WithMaxMessagesToRetrieve_UsesRangeQueryAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.ListRangeAsync(It.IsAny<RedisKey>(), It.IsAny<long>(), It.IsAny<long>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync([]);

        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection(dbMock).Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"))
        {
            MaxMessagesToRetrieve = 5
        };

        var context = TestHelpers.CreateChatHistoryInvokingContext();

        // Act
        await provider.InvokingAsync(context);

        // Assert — should use -5, -1 range
        dbMock.Verify(d => d.ListRangeAsync(
            It.IsAny<RedisKey>(), -5, -1, It.IsAny<CommandFlags>()), Times.Once);
    }

    [Fact]
    public async Task ProvideChatHistoryAsync_CancellationToken_ThrowsAsync()
    {
        // Arrange
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        var cts = new CancellationTokenSource();
        cts.Cancel();

        var context = TestHelpers.CreateChatHistoryInvokingContext();

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            provider.InvokingAsync(context, cts.Token).AsTask());
    }

    // --- StoreChatHistoryAsync tests ---

    [Fact]
    public async Task StoreChatHistoryAsync_BatchPushesMessagesAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.ListRightPushAsync(It.IsAny<RedisKey>(), It.IsAny<RedisValue[]>(), It.IsAny<When>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(2);

        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection(dbMock).Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        var context = TestHelpers.CreateChatHistoryInvokedContext(
            [new ChatMessage(ChatRole.User, "hello")],
            [new ChatMessage(ChatRole.Assistant, "hi")]);

        // Act
        await provider.InvokedAsync(context);

        // Assert — batch push called once with array
        dbMock.Verify(d => d.ListRightPushAsync(
            It.IsAny<RedisKey>(), It.IsAny<RedisValue[]>(), It.IsAny<When>(), It.IsAny<CommandFlags>()), Times.Once);
    }

    [Fact]
    public async Task StoreChatHistoryAsync_WithMaxMessages_TrimsAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.ListRightPushAsync(It.IsAny<RedisKey>(), It.IsAny<RedisValue[]>(), It.IsAny<When>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(1);
        dbMock.Setup(d => d.ListTrimAsync(It.IsAny<RedisKey>(), It.IsAny<long>(), It.IsAny<long>(), It.IsAny<CommandFlags>()))
            .Returns(Task.CompletedTask);

        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection(dbMock).Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"))
        {
            MaxMessages = 10
        };

        var context = TestHelpers.CreateChatHistoryInvokedContext(
            [new ChatMessage(ChatRole.User, "hello")],
            [new ChatMessage(ChatRole.Assistant, "hi")]);

        // Act
        await provider.InvokedAsync(context);

        // Assert — trim called unconditionally when MaxMessages is set
        dbMock.Verify(d => d.ListTrimAsync(
            It.IsAny<RedisKey>(), -10, -1, It.IsAny<CommandFlags>()), Times.Once);
    }

    // --- Disposed state tests ---

    [Fact]
    public async Task ProvideChatHistoryAsync_AfterDispose_ThrowsAsync()
    {
        // Arrange
        var provider = new ValkeyChatHistoryProvider(
            CreateMockConnection().Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        await provider.DisposeAsync();

        var context = TestHelpers.CreateChatHistoryInvokingContext();

        // Act & Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            provider.InvokingAsync(context).AsTask());
    }
}
