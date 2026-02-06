// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="InMemoryChatHistoryProvider"/> class.
/// </summary>
public class InMemoryChatHistoryProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static AgentSession CreateMockSession() => new Mock<AgentSession>().Object;

    [Fact]
    public void Constructor_DefaultsToBeforeMessageRetrieval_ForNotProvidedTriggerEvent()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object);

        // Assert
        Assert.Equal(InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval, provider.ReducerTriggerEvent);
    }

    [Fact]
    public void Constructor_Arguments_SetOnPropertiesCorrectly()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object, reducerTriggerEvent: InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded);

        // Assert
        Assert.Same(reducerMock.Object, provider.ChatReducer);
        Assert.Equal(InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded, provider.ReducerTriggerEvent);
    }

    [Fact]
    public async Task InvokedAsyncAddsMessagesAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "Hi there!")
        };
        var providerMessages = new List<ChatMessage>()
        {
            new(ChatRole.System, "original instructions")
        };
        var aiContextProviderMessages = new List<ChatMessage>()
        {
            new(ChatRole.System, "additional context")
        };

        var provider = new InMemoryChatHistoryProvider();
        provider.SetMessages(session, [providerMessages[0]]);
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, providerMessages)
        {
            AIContextProviderMessages = aiContextProviderMessages,
            ResponseMessages = responseMessages
        };
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        var messages = provider.GetMessages(session);
        Assert.Equal(4, messages.Count);
        Assert.Equal("original instructions", messages[0].Text);
        Assert.Equal("Hello", messages[1].Text);
        Assert.Equal("additional context", messages[2].Text);
        Assert.Equal("Hi there!", messages[3].Text);
    }

    [Fact]
    public async Task InvokedAsyncWithEmptyDoesNotFailAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, [], []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Empty(provider.GetMessages(session));
    }

    [Fact]
    public async Task InvokingAsyncReturnsAllMessagesAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.User, "Test1"),
            new ChatMessage(ChatRole.Assistant, "Test2")
        ]);

        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, []);
        var result = (await provider.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Contains(result, m => m.Text == "Test1");
        Assert.Contains(result, m => m.Text == "Test2");
    }

    [Fact]
    public void StateInitializer_IsInvoked_WhenSessionHasNoState()
    {
        // Arrange
        var initialMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Initial message")
        };
        var provider = new InMemoryChatHistoryProvider(
            stateInitializer: _ => new InMemoryChatHistoryProvider.State { Messages = initialMessages });

        // Act
        var messages = provider.GetMessages(CreateMockSession());

        // Assert
        Assert.Single(messages);
        Assert.Equal("Initial message", messages[0].Text);
    }

    [Fact]
    public void GetMessages_ReturnsEmptyList_WhenNullSession()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        // Act
        var messages = provider.GetMessages(null);

        // Assert
        Assert.Empty(messages);
    }

    [Fact]
    public void SetMessages_ThrowsForNullMessages()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => provider.SetMessages(CreateMockSession(), null!));
    }

    [Fact]
    public void SetMessages_UpdatesState()
    {
        var session = CreateMockSession();

        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "World")
        };

        // Act
        provider.SetMessages(session, messages);
        var retrieved = provider.GetMessages(session);

        // Assert
        Assert.Equal(2, retrieved.Count);
        Assert.Equal("Hello", retrieved[0].Text);
        Assert.Equal("World", retrieved[1].Text);
    }

    [Fact]
    public async Task InvokedAsyncWithEmptyMessagesDoesNotChangeProviderAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var messages = new List<ChatMessage>();

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, messages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Empty(provider.GetMessages(session));
    }

    [Fact]
    public async Task InvokedAsync_WithNullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokedAsync(null!, CancellationToken.None).AsTask());
    }

    [Fact]
    public async Task AddMessagesAsync_WithReducer_AfterMessageAdded_InvokesReducerAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var reducedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Reduced")
        };

        var reducerMock = new Mock<IChatReducer>();
        reducerMock
            .Setup(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()))
            .ReturnsAsync(reducedMessages);

        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object, reducerTriggerEvent: InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded);

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, originalMessages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        var messages = provider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("Reduced", messages[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task GetMessagesAsync_WithReducer_BeforeMessagesRetrieval_InvokesReducerAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var reducedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Reduced")
        };

        var reducerMock = new Mock<IChatReducer>();
        reducerMock
            .Setup(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()))
            .ReturnsAsync(reducedMessages);

        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object, reducerTriggerEvent: InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval);
        // Add messages directly to the provider for this test
        provider.SetMessages(session, new List<ChatMessage>(originalMessages));

        // Act
        var invokingContext = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, Array.Empty<ChatMessage>());
        var result = (await provider.InvokingAsync(invokingContext, CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Reduced", result[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task AddMessagesAsync_WithReducer_ButWrongTrigger_DoesNotInvokeReducerAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        var reducerMock = new Mock<IChatReducer>();

        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object, reducerTriggerEvent: InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval);

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, originalMessages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        var messages = provider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task GetMessagesAsync_WithReducer_ButWrongTrigger_DoesNotInvokeReducerAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        var reducerMock = new Mock<IChatReducer>();

        var provider = new InMemoryChatHistoryProvider(chatReducer: reducerMock.Object, reducerTriggerEvent: InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded);
        provider.SetMessages(session, new List<ChatMessage>(originalMessages));

        // Act
        var invokingContext = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, Array.Empty<ChatMessage>());
        var result = (await provider.InvokingAsync(invokingContext, CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Hello", result[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task InvokedAsync_WithException_DoesNotAddMessagesAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, [])
        {
            ResponseMessages = responseMessages,
            InvokeException = new InvalidOperationException("Test exception")
        };

        // Act
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Empty(provider.GetMessages(session));
    }

    [Fact]
    public async Task InvokingAsync_WithNullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokingAsync(null!, CancellationToken.None).AsTask());
    }

    public class TestAIContent(string testData) : AIContent
    {
        public string TestData => testData;
    }
}
