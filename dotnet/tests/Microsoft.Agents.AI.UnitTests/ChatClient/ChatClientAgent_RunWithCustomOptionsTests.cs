// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for <see cref="ChatClientAgent"/> run methods with <see cref="ChatClientAgentRunOptions"/>.
/// </summary>
public sealed partial class ChatClientAgent_RunWithCustomOptionsTests
{
    #region RunAsync Tests

    [Fact]
    public async Task RunAsync_WithThreadAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse result = await agent.RunAsync(thread, options);

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
    public async Task RunAsync_WithStringMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse result = await agent.RunAsync("Test message", thread, options);

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
    public async Task RunAsync_WithChatMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatMessage message = new(ChatRole.User, "Test message");
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse result = await agent.RunAsync(message, thread, options);

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
    public async Task RunAsync_WithMessagesCollectionAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        IEnumerable<ChatMessage> messages = [new(ChatRole.User, "Message 1"), new(ChatRole.User, "Message 2")];
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse result = await agent.RunAsync(messages, thread, options);

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
    public async Task RunAsync_WithChatOptionsInRunOptions_UsesChatOptionsAsync()
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
        AgentResponse result = await agent.RunAsync("Test", null, options);

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
    public async Task RunStreamingAsync_WithThreadAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentResponseUpdate>();
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
    public async Task RunStreamingAsync_WithStringMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentResponseUpdate>();
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
    public async Task RunStreamingAsync_WithChatMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatMessage message = new(ChatRole.User, "Test message");
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentResponseUpdate>();
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
    public async Task RunStreamingAsync_WithMessagesCollectionAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(GetAsyncUpdatesAsync());

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        IEnumerable<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Message 1"), new ChatMessage(ChatRole.User, "Message 2")];
        ChatClientAgentRunOptions options = new();

        // Act
        var updates = new List<AgentResponseUpdate>();
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

    #region Helper Methods

    private static async IAsyncEnumerable<ChatResponseUpdate> GetAsyncUpdatesAsync()
    {
        yield return new ChatResponseUpdate { Contents = new[] { new TextContent("Hello") } };
        yield return new ChatResponseUpdate { Contents = new[] { new TextContent(" World") } };
        await Task.CompletedTask;
    }

    #endregion

    #region RunAsync{T} Tests

    [Fact]
    public async Task RunAsyncOfT_WithThreadAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, """{"id":2, "fullName":"Tigger", "species":"Tiger"}""")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse<Animal> agentResponse = await agent.RunAsync<Animal>(thread, JsonContext_WithCustomRunOptions.Default.Options, options);

        // Assert
        Assert.NotNull(agentResponse);
        Assert.Single(agentResponse.Messages);
        Assert.Equal("Tigger", agentResponse.Result.FullName);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsyncOfT_WithStringMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, """{"id":2, "fullName":"Tigger", "species":"Tiger"}""")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse<Animal> agentResponse = await agent.RunAsync<Animal>("Test message", thread, JsonContext_WithCustomRunOptions.Default.Options, options);

        // Assert
        Assert.NotNull(agentResponse);
        Assert.Single(agentResponse.Messages);
        Assert.Equal("Tigger", agentResponse.Result.FullName);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Any(m => m.Text == "Test message")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsyncOfT_WithChatMessageAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, """{"id":2, "fullName":"Tigger", "species":"Tiger"}""")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        ChatMessage message = new(ChatRole.User, "Test message");
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse<Animal> agentResponse = await agent.RunAsync<Animal>(message, thread, JsonContext_WithCustomRunOptions.Default.Options, options);

        // Assert
        Assert.NotNull(agentResponse);
        Assert.Single(agentResponse.Messages);
        Assert.Equal("Tigger", agentResponse.Result.FullName);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Contains(message)),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsyncOfT_WithMessagesCollectionAndOptions_CallsBaseMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, """{"id":2, "fullName":"Tigger", "species":"Tiger"}""")]));

        ChatClientAgent agent = new(mockChatClient.Object);
        AgentThread thread = await agent.GetNewThreadAsync();
        IEnumerable<ChatMessage> messages = [new(ChatRole.User, "Message 1"), new(ChatRole.User, "Message 2")];
        ChatClientAgentRunOptions options = new();

        // Act
        AgentResponse<Animal> agentResponse = await agent.RunAsync<Animal>(messages, thread, JsonContext_WithCustomRunOptions.Default.Options, options);

        // Assert
        Assert.NotNull(agentResponse);
        Assert.Single(agentResponse.Messages);
        Assert.Equal("Tigger", agentResponse.Result.FullName);
        mockChatClient.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    private sealed class Animal
    {
        public int Id { get; set; }
        public string? FullName { get; set; }
        public Species Species { get; set; }
    }

    private enum Species
    {
        Bear,
        Tiger,
        Walrus,
    }

    [JsonSourceGenerationOptions(UseStringEnumConverter = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(Animal))]
    private sealed partial class JsonContext_WithCustomRunOptions : JsonSerializerContext;
}
