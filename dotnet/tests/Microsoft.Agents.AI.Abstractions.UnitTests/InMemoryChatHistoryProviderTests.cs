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
        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object });

        // Assert
        Assert.Equal(InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval, provider.ReducerTriggerEvent);
    }

    [Fact]
    public void Constructor_Arguments_SetOnPropertiesCorrectly()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded });

        // Assert
        Assert.Same(reducerMock.Object, provider.ChatReducer);
        Assert.Equal(InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded, provider.ReducerTriggerEvent);
    }

    [Fact]
    public void StateKeys_ReturnsDefaultKey_WhenNoOptionsProvided()
    {
        // Arrange & Act
        var provider = new InMemoryChatHistoryProvider();

        // Assert
        Assert.Single(provider.StateKeys);
        Assert.Contains("InMemoryChatHistoryProvider", provider.StateKeys);
    }

    [Fact]
    public void StateKeys_ReturnsCustomKey_WhenSetViaOptions()
    {
        // Arrange & Act
        var provider = new InMemoryChatHistoryProvider(new() { StateKey = "custom-key" });

        // Assert
        Assert.Single(provider.StateKeys);
        Assert.Contains("custom-key", provider.StateKeys);
    }

    [Fact]
    public async Task InvokedAsyncAddsMessagesAsync()
    {
        var session = CreateMockSession();

        // Arrange
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.System, "additional context") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "TestSource") } } },
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "Hi there!")
        };
        var providerMessages = new List<ChatMessage>()
        {
            new(ChatRole.System, "original instructions")
        };

        var provider = new InMemoryChatHistoryProvider();
        provider.SetMessages(session, providerMessages);
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, responseMessages);
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
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
        };

        var provider = new InMemoryChatHistoryProvider();
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.User, "Test1"),
            new ChatMessage(ChatRole.Assistant, "Test2")
        ]);

        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, requestMessages);
        var result = (await provider.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Contains(result, m => m.Text == "Test1");
        Assert.Contains(result, m => m.Text == "Test2");
        Assert.Contains(result, m => m.Text == "Hello");

        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result[0].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result[1].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.External, result[2].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public void StateInitializer_IsInvoked_WhenSessionHasNoState()
    {
        // Arrange
        var initialMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Initial message")
        };
        var provider = new InMemoryChatHistoryProvider(new()
        {
            StateInitializer = _ => new InMemoryChatHistoryProvider.State { Messages = initialMessages }
        });

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
        // Existing messages in state from a previous turn.
        var existingMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var reducedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Reduced")
        };

        // New messages being added in the current turn.
        var newRequestMessage = new ChatMessage(ChatRole.User, "New message");
        var newResponseMessage = new ChatMessage(ChatRole.Assistant, "New response");

        var reducerMock = new Mock<IChatReducer>();
        reducerMock
            .Setup(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(existingMessages)), It.IsAny<CancellationToken>()))
            .ReturnsAsync(reducedMessages);

        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded });
        provider.SetMessages(session, new List<ChatMessage>(existingMessages));

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, [newRequestMessage], [newResponseMessage]);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        // The reducer is called on existing messages before the new ones are added.
        reducerMock.Verify(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(existingMessages)), It.IsAny<CancellationToken>()), Times.Once);

        // Final state: reduced existing messages + new current-turn messages (preserved in full).
        var messages = provider.GetMessages(session);
        Assert.Equal(3, messages.Count);
        Assert.Equal("Reduced", messages[0].Text);
        Assert.Equal("New message", messages[1].Text);
        Assert.Equal("New response", messages[2].Text);
    }

    [Fact]
    public async Task AddMessagesAsync_WithReducer_AfterMessageAdded_PreservesCurrentTurnFunctionCallsAsync()
    {
        var session = CreateMockSession();

        // Arrange - verify that function call and tool result messages from the current turn are preserved
        // even when a reducer is configured with AfterMessageAdded trigger. The reducer should only
        // be applied to existing (previous-turn) messages, not to the new messages being added.
        var existingMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Previous question"),
            new(ChatRole.Assistant, "Previous answer")
        };

        var reducerMock = new Mock<IChatReducer>();
        reducerMock
            .Setup(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);  // Simulates an aggressive reducer that clears all messages it receives

        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded });
        provider.SetMessages(session, new List<ChatMessage>(existingMessages));

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "What is the weather in Taggia?")
        };
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, [new FunctionCallContent("call1", "GetWeather", new Dictionary<string, object?> { ["location"] = "Taggia" })]),
            new(ChatRole.Tool, [new FunctionResultContent("call1", "Cloudy with a high of 15°C")]),
            new(ChatRole.Assistant, "The weather in Taggia is cloudy with a high of 15°C.")
        };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, responseMessages);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert - all current-turn messages (including function call and tool result) are preserved
        var messages = provider.GetMessages(session);
        Assert.Equal(4, messages.Count);
        Assert.Equal("What is the weather in Taggia?", messages[0].Text);
        Assert.True(messages[1].Contents.OfType<FunctionCallContent>().Any(), "Function call message should be preserved");
        Assert.True(messages[2].Contents.OfType<FunctionResultContent>().Any(), "Tool result message should be preserved");
        Assert.Equal("The weather in Taggia is cloudy with a high of 15°C.", messages[3].Text);
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

        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval });
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

        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval });

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

        var provider = new InMemoryChatHistoryProvider(new() { ChatReducer = reducerMock.Object, ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded });
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
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, new InvalidOperationException("Test exception"));

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

    [Fact]
    public async Task InvokedAsync_DefaultFilter_ExcludesChatHistoryMessagesAsync()
    {
        // Arrange
        var session = CreateMockSession();
        var provider = new InMemoryChatHistoryProvider();
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert - ChatHistory message excluded, AIContextProvider message included
        var messages = provider.GetMessages(session);
        Assert.Equal(3, messages.Count);
        Assert.Equal("External message", messages[0].Text);
        Assert.Equal("From context provider", messages[1].Text);
        Assert.Equal("Response", messages[2].Text);
    }

    [Fact]
    public async Task InvokedAsync_CustomFilter_OverridesDefaultAsync()
    {
        // Arrange
        var session = CreateMockSession();
        var provider = new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
        {
            StorageInputRequestMessageFilter = messages => messages.Where(m => m.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.External)
        });
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, session, requestMessages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert - Custom filter keeps only External messages (both ChatHistory and AIContextProvider excluded)
        var messages = provider.GetMessages(session);
        Assert.Equal(2, messages.Count);
        Assert.Equal("External message", messages[0].Text);
        Assert.Equal("Response", messages[1].Text);
    }

    [Fact]
    public async Task InvokingAsync_OutputFilter_FiltersOutputMessagesAsync()
    {
        // Arrange
        var session = CreateMockSession();
        var provider = new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
        {
            ProvideOutputMessageFilter = messages => messages.Where(m => m.Role == ChatRole.User)
        });
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.User, "User message"),
            new ChatMessage(ChatRole.Assistant, "Assistant message"),
            new ChatMessage(ChatRole.System, "System message")
        ]);

        // Act
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, []);
        var result = (await provider.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert - Only user messages pass through the output filter
        Assert.Single(result);
        Assert.Equal("User message", result[0].Text);
    }

    public class TestAIContent(string testData) : AIContent
    {
        public string TestData => testData;
    }
}
