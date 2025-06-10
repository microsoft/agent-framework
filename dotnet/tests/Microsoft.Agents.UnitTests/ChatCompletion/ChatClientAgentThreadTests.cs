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

        // Get the thread from the response and cast to IMessagesRetrievableThread
        var thread = await agent.CreateThreadAsync();

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
        Assert.False(thread.IsDeleted); // Should not be deleted initially
    }
}
