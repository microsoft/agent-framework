// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for ChatClientAgent background responses functionality.
/// </summary>
public class ChatClientAgent_BackgroundResponsesTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunAsync_PropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        var continuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }));
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

        ChatClientAgentSession? session = new() { ConversationId = "conversation-id" };

        // Act
        await agent.RunAsync(session, options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken.InnerToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_WhenPropertiesSetInBothLocations_PrioritizesAgentRunOptionsOverChatOptionsAsync()
    {
        // Arrange
        var continuationToken1 = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }));
        var continuationToken2 = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }));
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

        ChatClientAgentSession? session = new() { ConversationId = "conversation-id" };

        ChatClientAgent agent = new(mockChatClient.Object);

        // Act
        await agent.RunAsync(session, options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2.InnerToken, capturedChatOptions.ContinuationToken);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsync_PropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh") { ConversationId = "conversation-id" },
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?") { ConversationId = "conversation-id" },
        ];

        var continuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) { InputMessages = [new ChatMessage()] };
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

        ChatClientAgentSession? session = new() { ConversationId = "conversation-id" };

        // Act
        await foreach (var _ in agent.RunStreamingAsync(session, options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);

        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken.InnerToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenPropertiesSetInBothLocations_PrioritizesAgentRunOptionsOverChatOptionsAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh") { ConversationId = "conversation-id" },
        ];

        var continuationToken1 = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) { InputMessages = [new ChatMessage()] };
        var continuationToken2 = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) { InputMessages = [new ChatMessage()] };
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

        var session = new ChatClientAgentSession() { ConversationId = "conversation-id" };

        // Act
        await foreach (var _ in agent.RunStreamingAsync(session, options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2.InnerToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_WhenContinuationTokenReceivedFromChatResponse_WrapsContinuationTokenAsync()
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

        ChatClientAgentSession? session = new();

        // Act
        var response = await agent.RunAsync([new(ChatRole.User, "hi")], session, options: runOptions);

        // Assert
        Assert.Same(continuationToken, (response.ContinuationToken as ChatClientAgentContinuationToken)?.InnerToken);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenContinuationTokenReceived_WrapsContinuationTokenAsync()
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

        ChatClientAgentSession? session = new();

        // Act
        var actualUpdates = new List<AgentResponseUpdate>();
        await foreach (var u in agent.RunStreamingAsync([new(ChatRole.User, "hi")], session, options: new ChatClientAgentRunOptions(new ChatOptions { AllowBackgroundResponses = true })))
        {
            actualUpdates.Add(u);
        }

        // Assert
        Assert.Equal(2, actualUpdates.Count);
        Assert.Same(token1, (actualUpdates[0].ContinuationToken as ChatClientAgentContinuationToken)?.InnerToken);
        Assert.Null(actualUpdates[1].ContinuationToken); // last update has null token
    }

    [Fact]
    public async Task RunAsync_WhenMessagesProvidedWithContinuationToken_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) };

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
    public async Task RunStreamingAsync_WhenMessagesProvidedWithContinuationToken_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) };

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
    public async Task RunAsync_WhenContinuationTokenProvided_SkipsSessionMessagePopulationAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock chat history provider that would normally provide messages
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKey).Returns("ChatHistoryProvider");
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync([new(ChatRole.User, "Message from chat history provider")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>(null, null);
        mockContextProvider.SetupGet(p => p.StateKey).Returns("Provider1");
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
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

        ChatClientAgent agent = new(mockChatClient.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            AIContextProviders = [mockContextProvider.Object]
        });

        // Create a session
        ChatClientAgentSession? session = new();

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))
        };

        // Act
        await agent.RunAsync([], session, options: runOptions);

        // Assert

        // With continuation token, session message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that chat history provider was never called due to continuation token
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Never(), ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Never(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task RunStreamingAsync_WhenContinuationTokenProvided_SkipsSessionMessagePopulationAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock chat history provider that would normally provide messages
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKey).Returns("ChatHistoryProvider");
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync([new(ChatRole.User, "Message from chat history provider")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>(null, null);
        mockContextProvider.SetupGet(p => p.StateKey).Returns("Provider1");
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
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

        ChatClientAgent agent = new(mockChatClient.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            AIContextProviders = [mockContextProvider.Object]
        });

        // Create a session
        ChatClientAgentSession? session = new();

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })) { InputMessages = [new ChatMessage()] }
        };

        // Act
        await agent.RunStreamingAsync(session, options: runOptions).ToListAsync();

        // Assert
        // With continuation token, session message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that chat history provider was never called due to continuation token
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Never(), ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Never(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task RunAsync_WhenNoSessionProvidedForBackgroundResponses_ThrowsInvalidOperationExceptionAsync()
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
    public async Task RunStreamingAsync_WhenNoSessionProvidedForBackgroundResponses_ThrowsInvalidOperationExceptionAsync()
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
    public async Task RunStreamingAsync_WhenInputMessagesPresentInContinuationToken_ResumesStreamingAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "continuation") { ConversationId = "conversation-id" },
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentSession? session = new() { ConversationId = "conversation-id" };

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))
            {
                InputMessages = [new ChatMessage(ChatRole.User, "previous message")]
            }
        };

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(session, options: runOptions))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);

        // Verify that the IChatClient was called
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenResponseUpdatesPresentInContinuationToken_ResumesStreamingAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "continuation") { ConversationId = "conversation-id" },
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentSession? session = new() { ConversationId = "conversation-id" };

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))
            {
                ResponseUpdates = [new ChatResponseUpdate(ChatRole.Assistant, "previous update")]
            }
        };

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(session, options: runOptions))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);

        // Verify that the IChatClient was called
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenResumingStreaming_UsesUpdatesFromInitialRunForContextProviderAndChatHistoryProviderAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "upon"),
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " a"),
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " time"),
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        List<ChatMessage> capturedMessagesAddedToProvider = [];
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKey).Returns("ChatHistoryProvider");
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, ct) => capturedMessagesAddedToProvider.AddRange(ctx.ResponseMessages ?? []))
            .Returns(new ValueTask());

        AIContextProvider.InvokedContext? capturedInvokedContext = null;
        var mockContextProvider = new Mock<AIContextProvider>(null, null);
        mockContextProvider.SetupGet(p => p.StateKey).Returns("Provider1");
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<AIContextProvider.InvokedContext, CancellationToken>((context, ct) => capturedInvokedContext = context)
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockChatClient.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            AIContextProviders = [mockContextProvider.Object]
        });

        ChatClientAgentSession? session = new();

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))
            {
                ResponseUpdates = [new ChatResponseUpdate(ChatRole.Assistant, "once ")]
            }
        };

        // Act
        await agent.RunStreamingAsync(session, options: runOptions).ToListAsync();

        // Assert
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>());
        Assert.Single(capturedMessagesAddedToProvider);
        Assert.Contains("once upon a time", capturedMessagesAddedToProvider[0].Text);

        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>());
        Assert.NotNull(capturedInvokedContext?.ResponseMessages);
        Assert.Single(capturedInvokedContext.ResponseMessages);
        Assert.Contains("once upon a time", capturedInvokedContext.ResponseMessages.ElementAt(0).Text);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenResumingStreaming_UsesInputMessagesFromInitialRunForContextProviderAndChatHistoryProviderAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(Array.Empty<ChatResponseUpdate>()));

        List<ChatMessage> capturedMessagesAddedToProvider = [];
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKey).Returns("ChatHistoryProvider");
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, ct) => capturedMessagesAddedToProvider.AddRange(ctx.RequestMessages))
            .Returns(new ValueTask());

        AIContextProvider.InvokedContext? capturedInvokedContext = null;
        var mockContextProvider = new Mock<AIContextProvider>(null, null);
        mockContextProvider.SetupGet(p => p.StateKey).Returns("Provider1");
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<AIContextProvider.InvokedContext, CancellationToken>((context, ct) => capturedInvokedContext = context)
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockChatClient.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            AIContextProviders = [mockContextProvider.Object]
        });

        ChatClientAgentSession? session = new();

        AgentRunOptions runOptions = new()
        {
            ContinuationToken = new ChatClientAgentContinuationToken(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))
            {
                InputMessages = [new ChatMessage(ChatRole.User, "Tell me a story")],
            }
        };

        // Act
        await agent.RunStreamingAsync(session, options: runOptions).ToListAsync();

        // Assert
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>());
        Assert.Single(capturedMessagesAddedToProvider);
        Assert.Contains("Tell me a story", capturedMessagesAddedToProvider[0].Text);

        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>());
        Assert.NotNull(capturedInvokedContext?.RequestMessages);
        Assert.Single(capturedInvokedContext.RequestMessages);
        Assert.Contains("Tell me a story", capturedInvokedContext.RequestMessages.ElementAt(0).Text);
    }

    [Fact]
    public async Task RunStreamingAsync_WhenResumingStreaming_SavesInputMessagesAndUpdatesInContinuationTokenAsync()
    {
        // Arrange
        List<ChatResponseUpdate> returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Once") { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) },
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " upon") { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) },
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " a") { ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) },
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " time"){ ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }) },
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentSession? session = new() { };

        List<ChatClientAgentContinuationToken> capturedContinuationTokens = [];

        ChatMessage userMessage = new(ChatRole.User, "Tell me a story");

        // Act

        // Do the initial run
        await foreach (var update in agent.RunStreamingAsync(userMessage, session))
        {
            capturedContinuationTokens.Add(Assert.IsType<ChatClientAgentContinuationToken>(update.ContinuationToken));
            break;
        }

        // Now resume the run using the captured continuation token
        returnUpdates.RemoveAt(0); // remove the first mock update as it was already processed
        var options = new AgentRunOptions { ContinuationToken = capturedContinuationTokens[0] };
        await foreach (var update in agent.RunStreamingAsync(session, options: options))
        {
            capturedContinuationTokens.Add(Assert.IsType<ChatClientAgentContinuationToken>(update.ContinuationToken));
        }

        // Assert
        Assert.Equal(4, capturedContinuationTokens.Count);

        // Verify that the first continuation token has the initial input and first update
        Assert.NotNull(capturedContinuationTokens[0].InputMessages);
        Assert.Single(capturedContinuationTokens[0].InputMessages!);
        Assert.Equal("Tell me a story", capturedContinuationTokens[0].InputMessages!.Last().Text);
        Assert.NotNull(capturedContinuationTokens[0].ResponseUpdates);
        Assert.Single(capturedContinuationTokens[0].ResponseUpdates!);
        Assert.Equal("Once", capturedContinuationTokens[0].ResponseUpdates![0].Text);

        // Verify the last continuation token has the input and all updates
        var lastToken = capturedContinuationTokens[^1];
        Assert.NotNull(lastToken.InputMessages);
        Assert.Single(lastToken.InputMessages!);
        Assert.Equal("Tell me a story", lastToken.InputMessages!.Last().Text);
        Assert.NotNull(lastToken.ResponseUpdates);
        Assert.Equal(4, lastToken.ResponseUpdates!.Count);
        Assert.Equal("Once", lastToken.ResponseUpdates!.ElementAt(0).Text);
        Assert.Equal(" upon", lastToken.ResponseUpdates!.ElementAt(1).Text);
        Assert.Equal(" a", lastToken.ResponseUpdates!.ElementAt(2).Text);
        Assert.Equal(" time", lastToken.ResponseUpdates!.ElementAt(3).Text);
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
