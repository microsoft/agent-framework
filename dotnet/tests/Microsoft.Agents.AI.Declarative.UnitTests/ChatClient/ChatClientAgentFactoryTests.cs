// Copyright (c) Microsoft. All rights reserved.
using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for <see cref="ChatClientAgentFactory"/>.
/// </summary>
public class ChatClientAgentFactoryTests
{
    private readonly Mock<IChatClient> _mockChatClient;
    private readonly Mock<IServiceProvider> _mockServiceProvider;
    private readonly Mock<ILoggerFactory> _mockLoggerFactory;

    public ChatClientAgentFactoryTests()
    {
        this._mockChatClient = new Mock<IChatClient>();
        this._mockServiceProvider = new Mock<IServiceProvider>();
        this._mockLoggerFactory = new Mock<ILoggerFactory>();
    }

    #region Constructor Tests

    [Fact]
    public void Constructor_InitializesWithCorrectSupportedTypes()
    {
        // Act
        var factory = new ChatClientAgentFactory();

        // Assert
        Assert.Contains(ChatClientAgentFactory.ChatClientAgentType, factory.Types);
        Assert.NotNull(this._mockChatClient);
        Assert.NotNull(this._mockServiceProvider);
        Assert.NotNull(this._mockLoggerFactory);
    }

    #endregion

}
