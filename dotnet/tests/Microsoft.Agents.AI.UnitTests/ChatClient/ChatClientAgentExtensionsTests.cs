// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for <see cref="ChatClientAgentExtensions"/> methods with <see cref="ChatClientAgentRunOptions"/>.
/// </summary>
public sealed class ChatClientAgentExtensionsTests
{
    #region RunAsync Tests

    [Fact]
    public async Task RunAsync_WithThreadAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentRunResponse result = await agent.RunAsync(thread, options);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_WithStringMessageAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentRunResponse result = await agent.RunAsync("Test message", thread, options);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Any(m => m.Text == "Test message")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_WithChatMessageAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatMessage message = new(ChatRole.User, "Test message");
        ChatClientAgentRunOptions options = new();

        // Act
        AgentRunResponse result = await agent.RunAsync(message, thread, options);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Contains(message)),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_WithMessagesCollectionAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        IEnumerable<ChatMessage> messages = [new(ChatRole.User, "Message 1"), new(ChatRole.User, "Message 2")];
        ChatClientAgentRunOptions options = new();

        // Act
        AgentRunResponse result = await agent.RunAsync(messages, thread, options);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_WithChatOptionsInRunOptions_UsesChatOptions()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        ChatClientAgentRunOptions options = new(new ChatOptions { Temperature = 0.5f });

        // Act
        AgentRunResponse result = await agent.RunAsync("Test", null, options);

        // Assert
        Assert.NotNull(result);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.Temperature == 0.5f),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region RunStreamingAsync Tests

    [Fact]
    public async Task RunStreamingAsync_WithThreadAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(thread, options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        mockChatClient.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_WithStringMessageAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync("Test message", thread, options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        mockChatClient.Verify(
            x => x.GetStreamingResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Any(m => m.Text == "Test message")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_WithChatMessageAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        ChatMessage message = new(ChatRole.User, "Test message");
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(message, thread, options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        mockChatClient.Verify(
            x => x.GetStreamingResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Contains(message)),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_WithMessagesCollectionAndOptions_CallsBaseMethod()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = agent.GetNewThread();
        IEnumerable<ChatMessage> messages = new[] { new ChatMessage(ChatRole.User, "Message 1"), new ChatMessage(ChatRole.User, "Message 2") };
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(messages, thread, options))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        mockChatClient.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region RunAsync<T> Tests

    // Note: Testing generic RunAsync methods is complex due to mock setup requirements.
    // The key functionality being tested here is that the extension methods properly
    // delegate to the base methods with the correct parameter conversion.
    // Integration tests cover the full end-to-end functionality.

    #endregion

    #region Helper Methods

    private static async IAsyncEnumerable<ChatResponseUpdate> GetAsyncUpdatesAsync()
    {
        yield return new ChatResponseUpdate { Contents = new[] { new TextContent("Hello") } };
        yield return new ChatResponseUpdate { Contents = new[] { new TextContent(" World") } };
        await Task.CompletedTask;
    }

    #endregion
}
