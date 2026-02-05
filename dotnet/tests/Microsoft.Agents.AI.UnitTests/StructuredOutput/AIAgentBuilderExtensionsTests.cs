// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentBuilderExtensions"/> class.
/// </summary>
public sealed class AIAgentBuilderExtensionsTests
{
    private readonly Mock<IChatClient> _chatClientMock;
    private readonly TestAIAgent _innerAgent;

    public AIAgentBuilderExtensionsTests()
    {
        this._chatClientMock = new Mock<IChatClient>();
        this._innerAgent = new TestAIAgent();

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "{\"result\": \"test\"}")]));
    }

    [Fact]
    public void UseStructuredOutput_WithNullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgentBuilder builder = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () =>
            builder.UseStructuredOutput(this._chatClientMock.Object));
    }

    [Fact]
    public void UseStructuredOutput_WithExplicitChatClient_BuildsStructuredOutputAgent()
    {
        // Arrange
        AIAgentBuilder builder = this._innerAgent.AsBuilder();

        // Act
        AIAgent agent = builder.UseStructuredOutput(this._chatClientMock.Object).Build();

        // Assert
        Assert.IsType<StructuredOutputAgent>(agent);
    }

    [Fact]
    public void UseStructuredOutput_WithNoChatClientParameter_ResolvesChatClientFromServices()
    {
        // Arrange
        ServiceCollection services = new();
        services.AddSingleton(this._chatClientMock.Object);
        ServiceProvider serviceProvider = services.BuildServiceProvider();

        AIAgentBuilder builder = this._innerAgent.AsBuilder();

        // Act
        AIAgent agent = builder.UseStructuredOutput().Build(serviceProvider);

        // Assert
        Assert.IsType<StructuredOutputAgent>(agent);
    }

    [Fact]
    public void UseStructuredOutput_WithNoChatClientAvailable_ThrowsInvalidOperationException()
    {
        // Arrange
        AIAgentBuilder builder = this._innerAgent.AsBuilder();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            builder.UseStructuredOutput().Build(services: null));

        Assert.Contains("IChatClient", exception.Message);
    }

    [Fact]
    public void UseStructuredOutput_WithConfigure_AppliesConfiguration()
    {
        // Arrange
        AIAgentBuilder builder = this._innerAgent.AsBuilder();
        bool configureInvoked = false;

        // Act
        AIAgent agent = builder.UseStructuredOutput(
            this._chatClientMock.Object,
            options =>
            {
                configureInvoked = true;
                options.ChatClientSystemMessage = "Custom system message";
            }).Build();

        // Assert
        Assert.True(configureInvoked);
        Assert.IsType<StructuredOutputAgent>(agent);
    }
}
