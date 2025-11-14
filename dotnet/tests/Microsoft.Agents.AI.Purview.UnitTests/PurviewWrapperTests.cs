// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Purview.UnitTests;

/// <summary>
/// Unit tests for the <see cref="PurviewWrapper"/> class.
/// </summary>
public sealed class PurviewWrapperTests : IDisposable
{
    private readonly Mock<IScopedContentProcessor> _mockProcessor;
    private readonly IChannelHandler _channelHandler;
    private readonly PurviewSettings _settings;
    private readonly PurviewWrapper _wrapper;

    public PurviewWrapperTests()
    {
        this._mockProcessor = new Mock<IScopedContentProcessor>();
        this._channelHandler = Mock.Of<IChannelHandler>();
        this._settings = new PurviewSettings("TestApp")
        {
            TenantId = "tenant-123",
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app-123"),
            BlockedPromptMessage = "Prompt blocked by policy",
            BlockedResponseMessage = "Response blocked by policy"
        };
        this._wrapper = new PurviewWrapper(this._mockProcessor.Object, this._settings, NullLogger.Instance, this._channelHandler);
    }

    #region ProcessChatContentAsync Tests

    [Fact]
    public async Task ProcessChatContentAsync_WithBlockedPrompt_ReturnsBlockedMessageAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Sensitive content that should be blocked")
        };
        var mockChatClient = new Mock<IChatClient>();

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((true, "user-123"));

        // Act
        var result = await this._wrapper.ProcessChatContentAsync(messages, null, mockChatClient.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.System, result.Messages[0].Role);
        Assert.Equal("Prompt blocked by policy", result.Messages[0].Text);
        mockChatClient.Verify(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ProcessChatContentAsync_WithAllowedPromptAndBlockedResponse_ReturnsBlockedMessageAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockChatClient = new Mock<IChatClient>();
        var innerResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Sensitive response"));

        mockChatClient.Setup(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        this._mockProcessor.SetupSequence(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123")) // Prompt allowed
            .ReturnsAsync((true, "user-123"));  // Response blocked

        // Act
        var result = await this._wrapper.ProcessChatContentAsync(messages, null, mockChatClient.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.System, result.Messages[0].Role);
        Assert.Equal("Response blocked by policy", result.Messages[0].Text);
    }

    [Fact]
    public async Task ProcessChatContentAsync_WithAllowedPromptAndResponse_ReturnsInnerResponseAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockChatClient = new Mock<IChatClient>();
        var innerResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Safe response"));

        mockChatClient.Setup(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123"));

        // Act
        var result = await this._wrapper.ProcessChatContentAsync(messages, null, mockChatClient.Object, CancellationToken.None);

        // Assert
        Assert.Same(innerResponse, result);
    }

    [Fact]
    public async Task ProcessChatContentAsync_WithIgnoreExceptions_ContinuesOnPromptErrorAsync()
    {
        // Arrange
        var settingsWithIgnore = new PurviewSettings("TestApp")
        {
            TenantId = "tenant-123",
            IgnoreExceptions = true,
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app-123")
        };
        var wrapper = new PurviewWrapper(this._mockProcessor.Object, settingsWithIgnore, NullLogger.Instance, this._channelHandler);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var expectedResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from inner client"));
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        this._mockProcessor.SetupSequence(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("Prompt processing error")); // Response processing succeeds

        // Act
        var result = await wrapper.ProcessChatContentAsync(messages, null, mockChatClient.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Same(expectedResponse, result);
    }

    [Fact]
    public async Task ProcessChatContentAsync_WithoutIgnoreExceptions_ThrowsOnPromptErrorAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockChatClient = new Mock<IChatClient>();

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("Prompt processing error"));

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._wrapper.ProcessChatContentAsync(messages, null, mockChatClient.Object, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessChatContentAsync_UsesConversationIdFromOptions_Async()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var options = new ChatOptions { ConversationId = "conversation-123" };
        var mockChatClient = new Mock<IChatClient>();
        var innerResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response"));

        mockChatClient.Setup(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            "conversation-123",
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123"));

        // Act
        await this._wrapper.ProcessChatContentAsync(messages, options, mockChatClient.Object, CancellationToken.None);

        // Assert
        this._mockProcessor.Verify(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            "conversation-123",
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()), Times.Exactly(2));
    }

    #endregion

    #region ProcessAgentContentAsync Tests

    [Fact]
    public async Task ProcessAgentContentAsync_WithBlockedPrompt_ReturnsBlockedMessageAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Sensitive content")
        };
        var mockAgent = new Mock<AIAgent>();

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((true, "user-123"));

        // Act
        var result = await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.System, result.Messages[0].Role);
        Assert.Equal("Prompt blocked by policy", result.Messages[0].Text);
        mockAgent.Verify(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ProcessAgentContentAsync_WithAllowedPromptAndBlockedResponse_ReturnsBlockedMessageAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockAgent = new Mock<AIAgent>();
        var innerResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Sensitive response"));

        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        this._mockProcessor.SetupSequence(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123")) // Prompt allowed
            .ReturnsAsync((true, "user-123"));  // Response blocked

        // Act
        var result = await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.System, result.Messages[0].Role);
        Assert.Equal("Response blocked by policy", result.Messages[0].Text);
    }

    [Fact]
    public async Task ProcessAgentContentAsync_WithAllowedPromptAndResponse_ReturnsInnerResponseAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockAgent = new Mock<AIAgent>();
        var innerResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Safe response"));

        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123"));

        // Act
        var result = await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.Same(innerResponse, result);
    }

    [Fact]
    public async Task ProcessAgentContentAsync_WithIgnoreExceptions_ContinuesOnErrorAsync()
    {
        // Arrange
        var settingsWithIgnore = new PurviewSettings("TestApp")
        {
            TenantId = "tenant-123",
            IgnoreExceptions = true,
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app-123")
        };
        var wrapper = new PurviewWrapper(this._mockProcessor.Object, settingsWithIgnore, NullLogger.Instance, this._channelHandler);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var expectedResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Response from inner agent"));
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        this._mockProcessor.SetupSequence(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("Prompt processing error"))
            .ReturnsAsync((false, "user-123")); // Response processing succeeds

        // Act
        var result = await wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Same(expectedResponse, result);
    }

    [Fact]
    public async Task ProcessAgentContentAsync_WithoutIgnoreExceptions_ThrowsOnErrorAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockAgent = new Mock<AIAgent>();

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("Processing error"));

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessAgentContentAsync_ExtractsThreadIdFromMessageAdditionalProperties_Async()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    { "conversationId", "conversation-from-props" }
                }
            }
        };

        var expectedResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Response"));
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            "conversation-from-props",
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((false, "user-123"));

        // Act
        var result = await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        this._mockProcessor.Verify(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            "conversation-from-props",
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()), Times.Exactly(2));
    }

    [Fact]
    public async Task ProcessAgentContentAsync_GeneratesThreadId_WhenNotProvidedAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var expectedResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Response"));
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        string? capturedThreadId = null;
        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, string, Activity, PurviewSettings, string, CancellationToken>(
                (_, threadId, _, _, _, _) => capturedThreadId = threadId)
            .ReturnsAsync((false, "user-123"));

        // Act
        var result = await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(capturedThreadId);
        Assert.True(Guid.TryParse(capturedThreadId, out _), "Generated thread ID should be a valid GUID");
    }

    [Fact]
    public async Task ProcessAgentContentAsync_PassesResolvedUserId_ToResponseProcessingAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var mockAgent = new Mock<AIAgent>();
        var innerResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Response"));

        mockAgent.Setup(x => x.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        var callCount = 0;
        string? firstCallUserId = null;
        string? secondCallUserId = null;

        this._mockProcessor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            It.IsAny<Activity>(),
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, string, Activity, PurviewSettings, string, CancellationToken>(
                (_, _, _, _, userId, _) =>
                {
                    if (callCount == 0)
                    {
                        firstCallUserId = userId;
                    }
                    else if (callCount == 1)
                    {
                        secondCallUserId = userId;
                    }
                    callCount++;
                })
            .ReturnsAsync((false, "resolved-user-456"));

        // Act
        await this._wrapper.ProcessAgentContentAsync(messages, null, null, mockAgent.Object, CancellationToken.None);

        // Assert
        Assert.Null(firstCallUserId); // First call (prompt) should have null userId
        Assert.Equal("resolved-user-456", secondCallUserId); // Second call (response) should have resolved userId from first call
    }

    #endregion

    public void Dispose()
    {
        this._wrapper.Dispose();
    }
}
