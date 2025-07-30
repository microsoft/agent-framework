// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

#pragma warning disable CS0162 // Unreachable code detected

namespace Microsoft.Extensions.AI.Agents.UnitTests.ChatCompletion;

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
        var agent = new ChatClientAgent(mockChatClient.Object, options: new()
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
        Assert.Null(thread.Id); // Id should be null until created on first use.
        Assert.Null(thread.StorageLocation); // StorageLocation should be null until first use
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> initializes with expected default values.
    /// </summary>
    [Fact]
    public async Task VerifyThreadWithMessagesInitialStateAsync()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.User, "Hello");

        // Act
        var thread = new ChatClientAgentThread([message]);

        // Assert
        Assert.Null(thread.Id); // Id should be null when we add messages, since it's a local thread.
        Assert.Equal(ChatClientAgentThreadType.InMemoryMessages, thread.StorageLocation); // StorageLocation should be set to local since we are adding messages already.

        var messages = await thread.GetMessagesAsync().ToListAsync();
        Assert.Contains(message, messages);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> initializes with expected default values.
    /// </summary>
    [Fact]
    public async Task VerifyThreadWithIdInitialStateAsync()
    {
        // Act
        var thread = new ChatClientAgentThread("TestConvId");

        // Assert
        Assert.Equal("TestConvId", thread.Id);
        Assert.Equal(ChatClientAgentThreadType.ConversationId, thread.StorageLocation);

        var messages = await thread.GetMessagesAsync().ToListAsync();
        Assert.Empty(messages);
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

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());

        // Act
        var thread = agent.GetNewThread();

        // Assert
        Assert.NotNull(thread);
        var chatClientAgentThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Null(thread.Id); // Id should be null until created on first use.
        Assert.Null(chatClientAgentThread.StorageLocation); // StorageLocation should be null until first use
    }

    /// <summary>
    /// Verify that thread creation generates unique instances.
    /// </summary>
    [Fact]
    public void ThreadCreationGeneratesUniqueInstances()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, options: new());

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
    [Theory]
    [InlineData(null, true)]
    [InlineData("TestConvid", false)]
    public async Task ThreadLifecycleStoresAndRetrievesMessagesAsync(string? responseConversationId, bool messagesStored)
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
            .ReturnsAsync(new ChatResponse([assistantMessage]) { ConversationId = responseConversationId });

        var agent = new ChatClientAgent(mockChatClient.Object, options: new() { Instructions = "Test instructions" });

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
        Assert.Equal(messagesStored ? 2 : 0, retrievedMessages.Count);
        if (messagesStored)
        {
            Assert.Contains(retrievedMessages, m => m.Text == "Hello" && m.Role == ChatRole.User);
            Assert.Contains(retrievedMessages, m => m.Text == "Hi there!" && m.Role == ChatRole.Assistant);
        }

        var chatClientAgentThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Equal(responseConversationId, thread.Id);  // Id should match the returned conversation id.
        Assert.Equal(
            messagesStored
                ? ChatClientAgentThreadType.InMemoryMessages
                : ChatClientAgentThreadType.ConversationId,
            chatClientAgentThread.StorageLocation);       // StorageLocation should be based on whether we got back a conversation id
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

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
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

    #region RunStreamingAsync Thread Notification Tests

    /// <summary>
    /// Verify that thread is notified of both input and response messages when invoking the streaming API with RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task VerifyThreadNotificationDuringStreamingAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello, streaming!");
        var assistantMessage = new ChatMessage(ChatRole.Assistant, "Hi there, streaming response!");

        // Create streaming response updates
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Hi there, "),
            new ChatResponseUpdate(role: null, content: "streaming response!"),
        ];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(returnUpdates.ToAsyncEnumerable());

        // Create ChatClientAgent with the mocked client
        var agent = new ChatClientAgent(mockChatClient.Object, options: new()
        {
            Instructions = "You are a helpful assistant"
        });

        // Get a new thread from the agent
        var thread = agent.GetNewThread();

        // Act - Run the agent with streaming to populate the thread with messages
        var streamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([userMessage], thread))
        {
            streamingResults.Add(update);
        }

        // Assert - Verify streaming worked
        Assert.Equal(2, streamingResults.Count);

        // Retrieve messages from the thread to verify notification occurred
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread was notified and contains both user and assistant messages
        Assert.NotEmpty(retrievedMessages);
        Assert.Equal(2, retrievedMessages.Count);
        Assert.Contains(retrievedMessages, m => m.Text == "Hello, streaming!" && m.Role == ChatRole.User);
        Assert.Contains(retrievedMessages, m => m.Text == "Hi there, streaming response!" && m.Role == ChatRole.Assistant);
    }

    /// <summary>
    /// Verify that thread accumulates both input and response messages across multiple streaming calls.
    /// </summary>
    [Fact]
    public async Task VerifyThreadAccumulatesMessagesAcrossMultipleStreamingCallsAsync()
    {
        // Arrange
        var firstUserMessage = new ChatMessage(ChatRole.User, "First streaming message");
        var secondUserMessage = new ChatMessage(ChatRole.User, "Second streaming message");

        // Create streaming response updates for first call
        ChatResponseUpdate[] firstReturnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "First "),
            new ChatResponseUpdate(role: null, content: "response"),
        ];

        // Create streaming response updates for second call
        ChatResponseUpdate[] secondReturnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Second "),
            new ChatResponseUpdate(role: null, content: "response"),
        ];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.SetupSequence(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(firstReturnUpdates.ToAsyncEnumerable())
            .Returns(secondReturnUpdates.ToAsyncEnumerable());

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act - Make two streaming calls
        var firstStreamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([firstUserMessage], thread))
        {
            firstStreamingResults.Add(update);
        }

        var secondStreamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([secondUserMessage], thread))
        {
            secondStreamingResults.Add(update);
        }

        // Assert - Verify both streaming calls worked
        Assert.Equal(2, firstStreamingResults.Count);
        Assert.Equal(2, secondStreamingResults.Count);

        // Retrieve all messages from the thread
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread contains all messages in order
        Assert.Equal(4, retrievedMessages.Count);
        Assert.Equal("First streaming message", retrievedMessages[0].Text);
        Assert.Equal("First response", retrievedMessages[1].Text);
        Assert.Equal("Second streaming message", retrievedMessages[2].Text);
        Assert.Equal("Second response", retrievedMessages[3].Text);
    }

    /// <summary>
    /// Verify that thread notification works correctly when streaming with existing thread messages.
    /// Both RunAsync and RunStreamingAsync should add both input and response messages to the thread.
    /// </summary>
    [Fact]
    public async Task VerifyStreamingWithExistingThreadMessagesAsync()
    {
        // Arrange
        var initialUserMessage = new ChatMessage(ChatRole.User, "Initial message");
        var initialAssistantMessage = new ChatMessage(ChatRole.Assistant, "Initial response");
        var newUserMessage = new ChatMessage(ChatRole.User, "New streaming message");

        // Setup for initial non-streaming call
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([initialAssistantMessage]));

        // Setup for streaming call
        ChatResponseUpdate[] streamingUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Streaming "),
            new ChatResponseUpdate(role: null, content: "response"),
        ];

        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(streamingUpdates.ToAsyncEnumerable());

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act - First, make a regular call to populate the thread
        await agent.RunAsync([initialUserMessage], thread);

        // Then make a streaming call
        var streamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([newUserMessage], thread))
        {
            streamingResults.Add(update);
        }

        // Assert - Verify streaming worked
        Assert.Equal(2, streamingResults.Count);

        // Retrieve all messages from the thread
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread contains all messages including the new streaming ones
        Assert.Equal(4, retrievedMessages.Count);
        Assert.Equal("Initial message", retrievedMessages[0].Text);
        Assert.Equal("Initial response", retrievedMessages[1].Text);
        Assert.Equal("New streaming message", retrievedMessages[2].Text);
        Assert.Equal("Streaming response", retrievedMessages[3].Text);
    }

    /// <summary>
    /// Verify that thread is notified of input messages even when zero streaming updates are received.
    /// </summary>
    [Fact]
    public async Task VerifyThreadNotificationWithZeroStreamingUpdatesAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello with no response!");

        // Create empty streaming response (no updates)
        ChatResponseUpdate[] returnUpdates = [];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(returnUpdates.ToAsyncEnumerable());

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act - Run the agent with streaming that returns no updates
        var streamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([userMessage], thread))
        {
            streamingResults.Add(update);
        }

        // Assert - Verify no streaming updates were received
        Assert.Empty(streamingResults);

        // Retrieve messages from the thread to verify notification occurred
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread was notified of input messages even with zero updates
        // The fallback mechanism should ensure input messages are added to the thread
        Assert.Single(retrievedMessages);
        Assert.Contains(retrievedMessages, m => m.Text == "Hello with no response!" && m.Role == ChatRole.User);
    }

    /// <summary>
    /// Verify that thread is notified of input messages only once even with multiple streaming updates.
    /// </summary>
    [Fact]
    public async Task VerifyThreadNotificationWithMultipleStreamingUpdatesAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello with many updates!");

        // Create multiple streaming response updates
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "First "),
            new ChatResponseUpdate(role: null, content: "update, "),
            new ChatResponseUpdate(role: null, content: "second "),
            new ChatResponseUpdate(role: null, content: "update, "),
            new ChatResponseUpdate(role: null, content: "third "),
            new ChatResponseUpdate(role: null, content: "update!"),
        ];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(returnUpdates.ToAsyncEnumerable());

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act - Run the agent with streaming that returns multiple updates
        var streamingResults = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([userMessage], thread))
        {
            streamingResults.Add(update);
        }

        // Assert - Verify all streaming updates were received
        Assert.Equal(6, streamingResults.Count);

        // Retrieve messages from the thread to verify notification occurred
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread contains both input and response messages
        // Input message should be added only once despite multiple updates
        Assert.Equal(2, retrievedMessages.Count);
        Assert.Contains(retrievedMessages, m => m.Text == "Hello with many updates!" && m.Role == ChatRole.User);
        Assert.Contains(retrievedMessages, m => m.Text == "First update, second update, third update!" && m.Role == ChatRole.Assistant);
    }

    /// <summary>
    /// Verify that thread is NOT notified of input messages when an exception occurs during streaming.
    /// </summary>
    [Fact]
    public async Task VerifyThreadNotNotifiedWhenStreamingThrowsExceptionAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello that will fail!");

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("Streaming failed"));

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act & Assert - Verify that streaming throws an exception
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync([userMessage], thread))
            {
                Assert.Fail("Should not yield updates.");
            }
        });

        // Retrieve messages from the thread to verify NO notification occurred
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread was NOT notified of any messages due to the exception
        // This ensures that failed operations don't leave the thread in an inconsistent state
        Assert.Empty(retrievedMessages);
    }

    /// <summary>
    /// Verify that thread is NOT notified of input messages when an exception occurs after some streaming updates.
    /// </summary>
    [Fact]
    public async Task VerifyThreadNotNotifiedWhenStreamingThrowsExceptionAfterUpdatesAsync()
    {
        // Arrange
        var userMessage = new ChatMessage(ChatRole.User, "Hello that will partially fail!");

        // Create an async enumerable that yields some updates then throws
        static async IAsyncEnumerable<ChatResponseUpdate> GetUpdatesWithExceptionAsync()
        {
            await Task.CompletedTask; // Simulate async operation
            throw new InvalidOperationException("Streaming failed after partial response");
            yield break;
        }

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(GetUpdatesWithExceptionAsync());

        var agent = new ChatClientAgent(mockChatClient.Object, options: new());
        var thread = agent.GetNewThread();

        // Act & Assert - Verify that streaming throws an exception after some updates
        var streamingResults = new List<AgentRunResponseUpdate>();
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync([userMessage], thread))
            {
                streamingResults.Add(update);
            }
        });

        // Verify that some updates were received before the exception
        Assert.Empty(streamingResults);

        // Retrieve messages from the thread to verify NO notification occurred
        var messagesRetrievableThread = (IMessagesRetrievableThread)thread;
        var retrievedMessages = new List<ChatMessage>();
        await foreach (var message in messagesRetrievableThread.GetMessagesAsync())
        {
            retrievedMessages.Add(message);
        }

        // Assert - Verify that the thread was NOT notified of any messages due to the exception
        // Even though some updates were received, the exception should prevent thread notification
        Assert.Empty(retrievedMessages);
    }

    #endregion

    #region JSON Serialization Tests

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> can be serialized to JSON and deserialized back correctly.
    /// </summary>
    [Fact]
    public void VerifyJsonSerializationRoundTrip_DefaultThread()
    {
        // Arrange
        var originalThread = new ChatClientAgentThread();

        // Act
        string json = JsonSerializer.Serialize(originalThread);
        var deserializedThread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);

        // Assert
        Assert.NotNull(deserializedThread);
        Assert.Equal(originalThread.Id, deserializedThread.Id);
        Assert.Equal(originalThread.StorageLocation, deserializedThread.StorageLocation);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> with ID can be serialized to JSON and deserialized back correctly.
    /// </summary>
    [Fact]
    public void VerifyJsonSerializationRoundTrip_ThreadWithId()
    {
        // Arrange
        var originalThread = new ChatClientAgentThread("test-conversation-id");

        // Act
        string json = JsonSerializer.Serialize(originalThread);
        var deserializedThread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);

        // Assert
        Assert.NotNull(deserializedThread);
        Assert.Equal("test-conversation-id", deserializedThread.Id);
        Assert.Equal(ChatClientAgentThreadType.ConversationId, deserializedThread.StorageLocation);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> with messages can be serialized to JSON and deserialized back correctly.
    /// </summary>
    [Fact]
    public async Task VerifyJsonSerializationRoundTrip_ThreadWithMessagesAsync()
    {
        // Arrange
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "Hello, world!"),
            new ChatMessage(ChatRole.Assistant, "Hi there! How can I help you?"),
            new ChatMessage(ChatRole.User, "What's the weather like?")
        };
        var originalThread = new ChatClientAgentThread(messages);

        // Act
        string json = JsonSerializer.Serialize(originalThread);
        var deserializedThread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);

        // Assert
        Assert.NotNull(deserializedThread);
        Assert.Equal(originalThread.Id, deserializedThread.Id);
        Assert.Equal(ChatClientAgentThreadType.InMemoryMessages, deserializedThread.StorageLocation);

        // Verify messages are preserved
        var originalMessages = await originalThread.GetMessagesAsync().ToListAsync();
        var deserializedMessages = await deserializedThread.GetMessagesAsync().ToListAsync();

        Assert.Equal(originalMessages.Count, deserializedMessages.Count);
        for (int i = 0; i < originalMessages.Count; i++)
        {
            Assert.Equal(originalMessages[i].Role, deserializedMessages[i].Role);
            Assert.Equal(originalMessages[i].Text, deserializedMessages[i].Text);
        }
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> serialization handles null properties correctly.
    /// </summary>
    [Fact]
    public void VerifyJsonSerialization_HandlesNullProperties()
    {
        // Arrange
        var thread = new ChatClientAgentThread();

        // Act
        string json = JsonSerializer.Serialize(thread);

        // Assert - StorageLocation is no longer serialized independently
        Assert.DoesNotContain("storageLocation", json, StringComparison.OrdinalIgnoreCase);

        // Verify deserialization handles empty JSON correctly
        var deserializedThread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);
        Assert.NotNull(deserializedThread);
        Assert.Null(deserializedThread.StorageLocation);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> serialization only includes messages for InMemoryMessages storage type.
    /// </summary>
    [Fact]
    public void VerifyJsonSerialization_OnlyIncludesMessagesForInMemoryStorage()
    {
        // Arrange - Create thread with conversation ID (server-side storage)
        var threadWithId = new ChatClientAgentThread("test-id");

        // Act
        string json = JsonSerializer.Serialize(threadWithId);

        // Assert - Messages should not be included for ConversationId storage, and storageLocation is not serialized
        Assert.DoesNotContain("\"messages\"", json, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"storageLocation\"", json, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("\"id\":\"test-id\"", json, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> serialization includes messages for InMemoryMessages storage type.
    /// </summary>
    [Fact]
    public void VerifyJsonSerialization_IncludesMessagesForInMemoryStorage()
    {
        // Arrange - Create thread with messages (in-memory storage)
        var messages = new[] { new ChatMessage(ChatRole.User, "Test message") };
        var threadWithMessages = new ChatClientAgentThread(messages);

        // Act
        string json = JsonSerializer.Serialize(threadWithMessages);

        // Assert - Messages should be included for InMemoryMessages storage, but storageLocation is not serialized
        Assert.Contains("\"messages\"", json, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"storageLocation\"", json, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Test message", json, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> deserialization handles missing properties gracefully.
    /// </summary>
    [Fact]
    public void VerifyJsonDeserialization_HandlesMissingProperties()
    {
        // Arrange - JSON with minimal properties
        string minimalJson = "{}";

        // Act
        var thread = JsonSerializer.Deserialize<ChatClientAgentThread>(minimalJson);

        // Assert
        Assert.NotNull(thread);
        Assert.Null(thread.Id);
        Assert.Null(thread.StorageLocation);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> deserialization handles invalid JSON gracefully.
    /// </summary>
    [Fact]
    public void VerifyJsonDeserialization_HandlesMalformedJson()
    {
        // Arrange - Invalid JSON structure
        string invalidJson = "{ invalid json";

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ChatClientAgentThread>(invalidJson));
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> deserialization handles invalid storage location values.
    /// This test is no longer relevant since storageLocation is not independently deserialized.
    /// </summary>
    [Fact]
    public void VerifyJsonDeserialization_HandlesInvalidStorageLocation()
    {
        // Arrange - JSON with ID (which will set storage location to ConversationId)
        string jsonWithId = @"{""id"":""test""}";

        // Act
        var thread = JsonSerializer.Deserialize<ChatClientAgentThread>(jsonWithId);

        // Assert - Storage location is determined by presence of ID
        Assert.NotNull(thread);
        Assert.Equal("test", thread.Id);
        Assert.Equal(ChatClientAgentThreadType.ConversationId, thread.StorageLocation);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> deserialization preserves messages correctly.
    /// </summary>
    [Fact]
    public async Task VerifyJsonDeserialization_PreservesMessagesCorrectlyAsync()
    {
        // Arrange - Create a thread with messages and serialize it to get the correct format
        var originalMessages = new[]
        {
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi there!")
        };
        var originalThread = new ChatClientAgentThread(originalMessages);

        // Serialize to get the actual format, then deserialize
        string json = JsonSerializer.Serialize(originalThread);
        var thread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);

        // Assert
        Assert.NotNull(thread);
        Assert.Equal(ChatClientAgentThreadType.InMemoryMessages, thread.StorageLocation);

        var messages = await thread.GetMessagesAsync().ToListAsync();
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal("Hello", messages[0].Text);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
        Assert.Equal("Hi there!", messages[1].Text);
    }

    /// <summary>
    /// Verify that <see cref="ChatClientAgentThread"/> serialization and deserialization works with complex message content.
    /// </summary>
    [Fact]
    public async Task VerifyJsonSerializationRoundTrip_ComplexMessageContentAsync()
    {
        // Arrange - Create messages with various content types
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "Simple text message"),
            new ChatMessage(ChatRole.Assistant, [
                new TextContent("Mixed content: "),
                new TextContent("multiple parts")
            ]),
            new ChatMessage(ChatRole.User, "Message with special characters: ñáéíóú !@#$%^&*()")
        };
        var originalThread = new ChatClientAgentThread(messages);

        // Act
        string json = JsonSerializer.Serialize(originalThread);
        var deserializedThread = JsonSerializer.Deserialize<ChatClientAgentThread>(json);

        // Assert
        Assert.NotNull(deserializedThread);

        var originalMessages = await originalThread.GetMessagesAsync().ToListAsync();
        var deserializedMessages = await deserializedThread.GetMessagesAsync().ToListAsync();

        Assert.Equal(originalMessages.Count, deserializedMessages.Count);

        // Verify complex content is preserved
        for (int i = 0; i < originalMessages.Count; i++)
        {
            Assert.Equal(originalMessages[i].Role, deserializedMessages[i].Role);
            Assert.Equal(originalMessages[i].Text, deserializedMessages[i].Text);
        }
    }

    #endregion
}
