// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentThreadTests
{
    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> implements <see cref="IMessagesRetrievableThread"/>.
    /// </summary>
    [Fact]
    public void VerifyChatClientAgentThreadImplementsIMessagesRetrievableThread()
    {
        // Arrange & Act
        var thread = new ChatClientAgentThread();

        // Assert
        Assert.IsAssignableFrom<IMessagesRetrievableThread>(thread);
        Assert.IsAssignableFrom<AgentThread>(thread);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> can retrieve messages through <see cref="IMessagesRetrievableThread.GetMessagesAsync"/>.
    /// This test verifies the interface works correctly when no messages have been added.
    /// </summary>
    [Fact]
    public async Task VerifyIMessagesRetrievableThreadGetMessagesAsyncWhenEmptyAsync()
    {
        // Arrange
        var thread = new ChatClientAgentThread();

        // Act - Retrieve messages when thread is empty
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in thread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert
        Assert.Empty(retrievedMessages);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> can retrieve messages through <see cref="IMessagesRetrievableThread.GetMessagesAsync"/>.
    /// This test verifies the interface works correctly when messages have been added via ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task VerifyIMessagesRetrievableThreadGetMessagesAsyncWhenNotEmptyAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello, how are you?");
        var assistantMessage = new ChatMessage(ChatRole.Assistant, "I'm doing well, thank you!");

        // Mock IChatClient to return the assistant message
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([assistantMessage]));

        // Create ChatClientAgent with the mocked client
        var agent = new ChatClientAgent(mockChatClient.Object, new()
        {
            Instructions = "You are a helpful assistant"
        });

        // Get a new thread from the agent
        var thread = agent.GetNewThread();

        // Run the agent again with the thread to populate it with messages
        var responseWithThread = await agent.RunAsync([userMessage], thread);
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;

        // Retrieve messages through the interface
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert
        Assert.NotEmpty(retrievedMessages);

        // Verify that the messages include the assistant response
        Assert.Collection(retrievedMessages,
            m => Assert.Equal(ChatRole.User, m.Role),
            m => Assert.Equal(ChatRole.Assistant, m.Role));

        // Verify the content matches what we expect
        Assert.Contains(retrievedMessages, m => m.Text == "Hello, how are you?" && m.Role == ChatRole.User);
        Assert.Contains(retrievedMessages, m => m.Text == "I'm doing well, thank you!" && m.Role == ChatRole.Assistant);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread.GetMessagesAsync"/> works with cancellation token.
    /// </summary>
    [Fact]
    public async Task VerifyGetMessagesAsyncWithCancellationTokenAsync()
    {
        // Arrange
        var thread = new ChatClientAgentThread();
        using var cts = new CancellationTokenSource();

        // Act - Test that GetMessagesAsync accepts cancellation token without throwing
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var msg in thread.GetMessagesAsync(cts.Token))
        {
            retrievedMessages.Add(msg);
        }

        // Assert - Should return empty list when no messages
        Assert.Empty(retrievedMessages);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> initializes with expected default values.
    /// </summary>
    [Fact]
    public void VerifyThreadInitialState()
    {
        // Arrange & Act
        var thread = new ChatClientAgentThread();

        // Assert
        Assert.Null(thread.Id); // Id should be null until created
    }

    #region Core Override Method Tests

    /// <summary>
    /// Verify that thread creation generates a valid thread ID through integration with ChatClientAgent.
    /// </summary>
    [Fact]
    public void ThreadCreationGeneratesValidThreadId()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "response")]));

        var agent = new ChatClientAgent(mockChatClient.Object, new());

        // Act
        var thread = agent.GetNewThread();

        // Assert
        Assert.NotNull(thread);
        Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Null(thread.Id); // Id should be null until the thread is actually used
    }

    /// <summary>
    /// Verify that thread creation generates unique instances.
    /// </summary>
    [Fact]
    public void ThreadCreationGeneratesUniqueInstances()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new());

        // Act
        var thread1 = agent.GetNewThread();
        var thread2 = agent.GetNewThread();

        // Assert
        Assert.NotSame(thread1, thread2);
        Assert.IsType<ChatClientAgentThread>(thread1);
        Assert.IsType<ChatClientAgentThread>(thread2);
    }

    /// <summary>
    /// Verify that messages are properly stored and retrieved through the thread lifecycle.
    /// </summary>
    [Fact]
    public async Task ThreadLifecycleStoresAndRetrievesMessagesAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello");
        var assistantMessage = new ChatMessage(ChatRole.Assistant, "Hi there!");

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([assistantMessage]));

        var agent = new ChatClientAgent(mockChatClient.Object, new() { Instructions = "Test instructions" });

        // Act
        var thread = agent.GetNewThread();

        // Run the agent to populate the thread with messages
        await agent.RunAsync([userMessage], thread);

        // Retrieve messages from the thread
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in ((IMessagesRetrievableThread)thread).GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert
        Assert.Equal(2, retrievedMessages.Count);
        Assert.Contains(retrievedMessages, m => m.Text == "Hello" && m.Role == ChatRole.User);
        Assert.Contains(retrievedMessages, m => m.Text == "Hi there!" && m.Role == ChatRole.Assistant);
    }

    /// <summary>
    /// Verify that multiple messages can be added and retrieved in order.
    /// </summary>
    [Fact]
    public async Task ThreadMessageHandlingHandlesMultipleMessagesInOrderAsync()
    {
        // Arrange
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.Assistant, "First response"),
            new ChatMessage(ChatRole.User, "Second message"),
            new ChatMessage(ChatRole.Assistant, "Second response")
        };

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.SetupSequence(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([messages[1]]))
            .ReturnsAsync(new ChatResponse([messages[3]]));

        var agent = new ChatClientAgent(mockChatClient.Object, new());
        var thread = agent.GetNewThread();

        // Act - Add messages through multiple agent runs
        await agent.RunAsync([messages[0]], thread);
        await agent.RunAsync([messages[2]], thread);

        // Assert - Verify all messages are stored in order
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in ((IMessagesRetrievableThread)thread).GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        Assert.Equal(4, retrievedMessages.Count);
        Assert.Equal("First message", retrievedMessages[0].Text);
        Assert.Equal("First response", retrievedMessages[1].Text);
        Assert.Equal("Second message", retrievedMessages[2].Text);
        Assert.Equal("Second response", retrievedMessages[3].Text);
    }

    #endregion
}
