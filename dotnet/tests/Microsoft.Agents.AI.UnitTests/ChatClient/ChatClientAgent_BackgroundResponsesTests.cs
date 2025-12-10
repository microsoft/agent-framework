// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for ChatClientAgent background responses functionality.
/// </summary>
public class ChatClientAgent_BackgroundResponsesTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunAsyncPropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        var continuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ContinuationToken = null, ConversationId = "conversation-id" });

        AgentRunOptions agentRunOptions;

        if (providePropsViaChatOptions)
        {
            ChatOptions chatOptions = new()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };

            agentRunOptions = new ChatClientAgentRunOptions(chatOptions);
        }
        else
        {
            agentRunOptions = new AgentRunOptions()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };
        }

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new() { ConversationId = "conversation-id" };

        // Act
        await agent.RunAsync(thread, options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsyncPrioritizesBackgroundResponsesPropertiesFromAgentRunOptionsOverOnesFromChatOptionsAsync()
    {
        // Arrange
        var continuationToken1 = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        var continuationToken2 = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ContinuationToken = null, ConversationId = "conversation-id" });

        ChatOptions chatOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = continuationToken1
        };

        ChatClientAgentRunOptions agentRunOptions = new(chatOptions)
        {
            AllowBackgroundResponses = false,
            ContinuationToken = continuationToken2
        };

        ChatClientAgentThread thread = new() { ConversationId = "conversation-id" };

        ChatClientAgent agent = new(mockChatClient.Object);

        // Act
        await agent.RunAsync(thread, options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2, capturedChatOptions.ContinuationToken);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsyncPropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh") { ConversationId = "conversation-id" },
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?") { ConversationId = "conversation-id" },
        ];

        var continuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        AgentRunOptions agentRunOptions;

        if (providePropsViaChatOptions)
        {
            ChatOptions chatOptions = new()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };

            agentRunOptions = new ChatClientAgentRunOptions(chatOptions);
        }
        else
        {
            agentRunOptions = new AgentRunOptions()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };
        }

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new() { ConversationId = "conversation-id" };

        // Act
        await foreach (var _ in agent.RunStreamingAsync(thread, options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);

        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsyncPrioritizesBackgroundResponsesPropertiesFromAgentRunOptionsOverOnesFromChatOptionsAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh") { ConversationId = "conversation-id" },
        ];

        var continuationToken1 = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        var continuationToken2 = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatOptions chatOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = continuationToken1
        };

        ChatClientAgentRunOptions agentRunOptions = new(chatOptions)
        {
            AllowBackgroundResponses = false,
            ContinuationToken = continuationToken2
        };

        ChatClientAgent agent = new(mockChatClient.Object);

        var thread = new ChatClientAgentThread() { ConversationId = "conversation-id" };

        // Act
        await foreach (var _ in agent.RunStreamingAsync(thread, options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsyncPropagatesContinuationTokenFromChatResponseToAgentRunResponseAsync()
    {
        // Arrange
        var continuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "partial")]) { ContinuationToken = continuationToken });

        ChatClientAgent agent = new(mockChatClient.Object);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { AllowBackgroundResponses = true });

        ChatClientAgentThread thread = new();

        // Act
        var response = await agent.RunAsync([new(ChatRole.User, "hi")], thread, options: runOptions);

        // Assert
        Assert.Same(continuationToken, response.ContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsyncPropagatesContinuationTokensFromUpdatesAsync()
    {
        // Arrange
        var token1 = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        ChatResponseUpdate[] expectedUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "pa") { ContinuationToken = token1 },
            new ChatResponseUpdate(ChatRole.Assistant, "rt") { ContinuationToken = null } // terminal
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(expectedUpdates));

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new();

        // Act
        var actualUpdates = new List<AgentRunResponseUpdate>();
        await foreach (var u in agent.RunStreamingAsync([new(ChatRole.User, "hi")], thread, options: new ChatClientAgentRunOptions(new ChatOptions { AllowBackgroundResponses = true })))
        {
            actualUpdates.Add(u);
        }

        // Assert
        Assert.Equal(2, actualUpdates.Count);
        Assert.Same(token1, actualUpdates[0].ContinuationToken);
        Assert.Null(actualUpdates[1].ContinuationToken); // last update has null token
    }

    [Fact]
    public async Task RunAsyncThrowsWhenMessagesProvidedWithContinuationTokenAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(inputMessages, options: runOptions));

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenMessagesProvidedWithContinuationTokenAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(inputMessages, options: runOptions))
            {
                // Should not reach here
            }
        });

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAsyncSkipsThreadMessagePopulationWithContinuationTokenAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock message store that would normally provide messages
        var mockMessageStore = new Mock<ChatMessageStore>();
        mockMessageStore
            .Setup(ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync([new(ChatRole.User, "Message from message store")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>();
        mockContextProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = [new(ChatRole.System, "Message from AI context")],
                Instructions = "context instructions"
            });

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "continued response")]));

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a thread with both message store and AI context provider
        ChatClientAgentThread thread = new()
        {
            MessageStore = mockMessageStore.Object,
            AIContextProvider = mockContextProvider.Object
        };

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act
        await agent.RunAsync([], thread, options: runOptions);

        // Assert

        // With continuation token, thread message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that message store was never called due to continuation token
        mockMessageStore.Verify(
            ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()),
            Times.Never);

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider.Verify(
            p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncSkipsThreadMessagePopulationWithContinuationTokenAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock message store that would normally provide messages
        var mockMessageStore = new Mock<ChatMessageStore>();
        mockMessageStore
            .Setup(ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync([new(ChatRole.User, "Message from message store")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>();
        mockContextProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = [new(ChatRole.System, "Message from AI context")],
                Instructions = "context instructions"
            });

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .Returns(ToAsyncEnumerableAsync([new ChatResponseUpdate(role: ChatRole.Assistant, content: "continued response")]));

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a thread with both message store and AI context provider
        ChatClientAgentThread thread = new()
        {
            MessageStore = mockMessageStore.Object,
            AIContextProvider = mockContextProvider.Object
        };

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act
        var exception = await Assert.ThrowsAsync<NotSupportedException>(async () => await agent.RunStreamingAsync(thread, options: runOptions).ToListAsync());

        // Assert
        Assert.Equal("Streaming resumption is only supported when chat history is stored and managed by the underlying AI service.", exception.Message);

        // With continuation token, thread message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that message store was never called due to continuation token
        mockMessageStore.Verify(
            ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()),
            Times.Never);

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider.Verify(
            p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAsyncThrowsWhenNoThreadProvideForBackgroundResponsesAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { AllowBackgroundResponses = true };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(inputMessages, options: runOptions));

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenNoThreadProvideForBackgroundResponsesAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { AllowBackgroundResponses = true };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(inputMessages, options: runOptions))
            {
                // Should not reach here
            }
        });

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAsyncThrowsWhenContinuationTokenProvidedForInitialRunAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a new thread with no ConversationId and no MessageStore (initial run state)
        ChatClientAgentThread thread = new();

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(thread: thread, options: runOptions));
        Assert.Equal("Continuation tokens are not allowed to be used for initial runs.", exception.Message);

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenContinuationTokenProvidedForInitialRunAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a new thread with no ConversationId and no MessageStore (initial run state)
        ChatClientAgentThread thread = new();

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await agent.RunStreamingAsync(thread: thread, options: runOptions).ToListAsync());
        Assert.Equal("Continuation tokens are not allowed to be used for initial runs.", exception.Message);

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenContinuationTokenUsedWithClientSideManagedChatHistoryAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a thread with a MessageStore
        ChatClientAgentThread thread = new()
        {
            MessageStore = new InMemoryChatMessageStore(), // Setting a message store to skip checking the continuation token in the initial run
            ConversationId = null, // No conversation ID to simulate client-side managed chat history
        };

        // Create run options with a continuation token
        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<NotSupportedException>(async () => await agent.RunStreamingAsync(thread: thread, options: runOptions).ToListAsync());
        Assert.Equal("Streaming resumption is only supported when chat history is stored and managed by the underlying AI service.", exception.Message);

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenContinuationTokenUsedWithAIContextProviderAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a mock AIContextProvider
        var mockContextProvider = new Mock<AIContextProvider>();
        mockContextProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext());
        mockContextProvider
            .Setup(p => p.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask());

        // Create a thread with an AIContextProvider and conversation ID to simulate non-initial run
        ChatClientAgentThread thread = new()
        {
            ConversationId = "existing-conversation-id",
            AIContextProvider = mockContextProvider.Object
        };

        AgentRunOptions runOptions = new() { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<NotSupportedException>(async () => await agent.RunStreamingAsync(thread: thread, options: runOptions).ToListAsync());

        Assert.Equal("Using context provider with streaming resumption is not supported.", exception.Message);

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var update in values)
        {
            yield return update;
        }
    }
}
