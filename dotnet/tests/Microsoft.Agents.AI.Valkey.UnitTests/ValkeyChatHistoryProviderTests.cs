// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Valkey;
using Moq;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

/// <summary>
/// Unit tests for <see cref="ValkeyChatHistoryProvider"/>.
/// </summary>
public sealed class ValkeyChatHistoryProviderTests
{
    [Fact]
    public void Constructor_WithConnection_SetsProperties()
    {
        // Arrange
        var mockConnection = new Mock<IConnectionMultiplexer>();
        Func<AgentSession?, ValkeyChatHistoryProvider.State> stateInit =
            _ => new ValkeyChatHistoryProvider.State("conv-1");

        // Act
        var provider = new ValkeyChatHistoryProvider(
            mockConnection.Object,
            stateInit,
            keyPrefix: "test_prefix");

        // Assert
        Assert.NotNull(provider);
        Assert.Null(provider.MaxMessages);
        Assert.Null(provider.MaxMessagesToRetrieve);
    }

    [Fact]
    public void Constructor_WithConnection_NullConnection_Throws()
    {
        // Arrange
        Func<AgentSession?, ValkeyChatHistoryProvider.State> stateInit =
            _ => new ValkeyChatHistoryProvider.State("conv-1");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyChatHistoryProvider(
                (IConnectionMultiplexer)null!,
                stateInit));
    }

    [Fact]
    public void Constructor_WithConnection_NullStateInitializer_Throws()
    {
        // Arrange
        var mockConnection = new Mock<IConnectionMultiplexer>();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyChatHistoryProvider(
                mockConnection.Object,
                null!));
    }

    [Fact]
    public void State_NullConversationId_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyChatHistoryProvider.State(null!));
    }

    [Fact]
    public void State_EmptyConversationId_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new ValkeyChatHistoryProvider.State(""));
    }

    [Fact]
    public void State_ValidConversationId_SetsProperty()
    {
        // Act
        var state = new ValkeyChatHistoryProvider.State("my-conversation");

        // Assert
        Assert.Equal("my-conversation", state.ConversationId);
    }

    [Fact]
    public void StateKeys_ReturnsProviderTypeName()
    {
        // Arrange
        var mockConnection = new Mock<IConnectionMultiplexer>();
        var provider = new ValkeyChatHistoryProvider(
            mockConnection.Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"));

        // Act
        var keys = provider.StateKeys;

        // Assert
        Assert.Single(keys);
        Assert.Equal(nameof(ValkeyChatHistoryProvider), keys[0]);
    }

    [Fact]
    public void StateKeys_WithCustomKey_ReturnsCustomKey()
    {
        // Arrange
        var mockConnection = new Mock<IConnectionMultiplexer>();
        var provider = new ValkeyChatHistoryProvider(
            mockConnection.Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"),
            stateKey: "custom_key");

        // Act
        var keys = provider.StateKeys;

        // Assert
        Assert.Single(keys);
        Assert.Equal("custom_key", keys[0]);
    }

    [Fact]
    public void MaxMessages_CanBeSet()
    {
        // Arrange
        var mockConnection = new Mock<IConnectionMultiplexer>();
        var provider = new ValkeyChatHistoryProvider(
            mockConnection.Object,
            _ => new ValkeyChatHistoryProvider.State("conv-1"))
        {
            MaxMessages = 50
        };

        // Assert
        Assert.Equal(50, provider.MaxMessages);
    }
}
