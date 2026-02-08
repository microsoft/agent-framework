// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
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
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    [Fact]
    public void Constructor_Throws_ForNullReducer() =>
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new InMemoryChatHistoryProvider(null!));

    [Fact]
    public void Constructor_DefaultsToBeforeMessageRetrieval_ForNotProvidedTriggerEvent()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var provider = new InMemoryChatHistoryProvider(reducerMock.Object);

        // Assert
        Assert.Equal(InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval, provider.ReducerTriggerEvent);
    }

    [Fact]
    public void Constructor_Arguments_SetOnPropertiesCorrectly()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var provider = new InMemoryChatHistoryProvider(reducerMock.Object, InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded);

        // Assert
        Assert.Same(reducerMock.Object, provider.ChatReducer);
        Assert.Equal(InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded, provider.ReducerTriggerEvent);
    }

    [Fact]
    public async Task InvokedAsyncAddsMessagesAsync()
    {
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
        provider.Add(providerMessages[0]);
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, providerMessages)
        {
            AIContextProviderMessages = aiContextProviderMessages,
            ResponseMessages = responseMessages
        };
        await provider.InvokedAsync(context, CancellationToken.None);

        Assert.Equal(4, provider.Count);
        Assert.Equal("original instructions", provider[0].Text);
        Assert.Equal("Hello", provider[1].Text);
        Assert.Equal("additional context", provider[2].Text);
        Assert.Equal("Hi there!", provider[3].Text);
    }

    [Fact]
    public async Task InvokedAsyncWithEmptyDoesNotFailAsync()
    {
        var provider = new InMemoryChatHistoryProvider();

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, [], []);
        await provider.InvokedAsync(context, CancellationToken.None);

        Assert.Empty(provider);
    }

    [Fact]
    public async Task InvokingAsyncReturnsAllMessagesAsync()
    {
        var provider = new InMemoryChatHistoryProvider
        {
            new ChatMessage(ChatRole.User, "Test1"),
            new ChatMessage(ChatRole.Assistant, "Test2")
        };

        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, []);
        var result = (await provider.InvokingAsync(context, CancellationToken.None)).ToList();

        Assert.Equal(2, result.Count);
        Assert.Contains(result, m => m.Text == "Test1");
        Assert.Contains(result, m => m.Text == "Test2");
    }

    [Fact]
    public async Task DeserializeConstructorWithEmptyElementAsync()
    {
        var emptyObject = JsonSerializer.Deserialize("{}", TestJsonSerializerContext.Default.JsonElement);

        var newProvider = new InMemoryChatHistoryProvider(emptyObject);

        Assert.Empty(newProvider);
    }

    [Fact]
    public async Task SerializeAndDeserializeConstructorRoundtripsAsync()
    {
        var provider = new InMemoryChatHistoryProvider
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B")
        };

        var jsonElement = provider.Serialize();
        var newProvider = new InMemoryChatHistoryProvider(jsonElement);

        Assert.Equal(2, newProvider.Count);
        Assert.Equal("A", newProvider[0].Text);
        Assert.Equal("B", newProvider[1].Text);
    }

    [Fact]
    public async Task SerializeAndDeserializeConstructorRoundtripsWithCustomAIContentAsync()
    {
        JsonSerializerOptions options = new(TestJsonSerializerContext.Default.Options)
        {
            TypeInfoResolver = JsonTypeInfoResolver.Combine(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver, TestJsonSerializerContext.Default),
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };
        options.AddAIContentType<TestAIContent>(typeDiscriminatorId: "testContent");

        var provider = new InMemoryChatHistoryProvider
        {
            new ChatMessage(ChatRole.User, [new TestAIContent("foo data")]),
        };

        var jsonElement = provider.Serialize(options);
        var newProvider = new InMemoryChatHistoryProvider(jsonElement, options);

        Assert.Single(newProvider);
        var actualTestAIContent = Assert.IsType<TestAIContent>(newProvider[0].Contents[0]);
        Assert.Equal("foo data", actualTestAIContent.TestData);
    }

    [Fact]
    public async Task SerializeAndDeserializeWorksWithExperimentalContentTypesAsync()
    {
        var provider = new InMemoryChatHistoryProvider
        {
            new ChatMessage(ChatRole.User, [new FunctionApprovalRequestContent("call123", new FunctionCallContent("call123", "some_func"))]),
            new ChatMessage(ChatRole.Assistant, [new FunctionApprovalResponseContent("call123", true, new FunctionCallContent("call123", "some_func"))])
        };

        var jsonElement = provider.Serialize();
        var newProvider = new InMemoryChatHistoryProvider(jsonElement);

        Assert.Equal(2, newProvider.Count);
        Assert.IsType<FunctionApprovalRequestContent>(newProvider[0].Contents[0]);
        Assert.IsType<FunctionApprovalResponseContent>(newProvider[1].Contents[0]);
    }

    [Fact]
    public async Task InvokedAsyncWithEmptyMessagesDoesNotChangeProviderAsync()
    {
        var provider = new InMemoryChatHistoryProvider();
        var messages = new List<ChatMessage>();

        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, messages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        Assert.Empty(provider);
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
    public void DeserializeContructor_WithNullSerializedState_CreatesEmptyProvider()
    {
        // Act
        var provider = new InMemoryChatHistoryProvider(new JsonElement());

        // Assert
        Assert.Empty(provider);
    }

    [Fact]
    public async Task DeserializeContructor_WithEmptyMessages_DoesNotAddMessagesAsync()
    {
        // Arrange
        var stateWithEmptyMessages = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["messages"] = new List<ChatMessage>() },
            TestJsonSerializerContext.Default.IDictionaryStringObject);

        // Act
        var provider = new InMemoryChatHistoryProvider(stateWithEmptyMessages);

        // Assert
        Assert.Empty(provider);
    }

    [Fact]
    public async Task DeserializeConstructor_WithNullMessages_DoesNotAddMessagesAsync()
    {
        // Arrange
        var stateWithNullMessages = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["messages"] = null! },
            TestJsonSerializerContext.Default.DictionaryStringObject);

        // Act
        var provider = new InMemoryChatHistoryProvider(stateWithNullMessages);

        // Assert
        Assert.Empty(provider);
    }

    [Fact]
    public async Task DeserializeConstructor_WithValidMessages_AddsMessagesAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "User message"),
            new(ChatRole.Assistant, "Assistant message")
        };
        var state = new Dictionary<string, object> { ["messages"] = messages };
        var serializedState = JsonSerializer.SerializeToElement(
            state,
            TestJsonSerializerContext.Default.DictionaryStringObject);

        // Act
        var provider = new InMemoryChatHistoryProvider(serializedState);

        // Assert
        Assert.Equal(2, provider.Count);
        Assert.Equal("User message", provider[0].Text);
        Assert.Equal("Assistant message", provider[1].Text);
    }

    [Fact]
    public void IndexerGet_ReturnsCorrectMessage()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);
        provider.Add(message2);

        // Act & Assert
        Assert.Same(message1, provider[0]);
        Assert.Same(message2, provider[1]);
    }

    [Fact]
    public void IndexerSet_UpdatesMessage()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var originalMessage = new ChatMessage(ChatRole.User, "Original");
        var newMessage = new ChatMessage(ChatRole.User, "Updated");
        provider.Add(originalMessage);

        // Act
        provider[0] = newMessage;

        // Assert
        Assert.Same(newMessage, provider[0]);
        Assert.Equal("Updated", provider[0].Text);
    }

    [Fact]
    public void IsReadOnly_ReturnsFalse()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();

        // Act & Assert
        Assert.False(provider.IsReadOnly);
    }

    [Fact]
    public void IndexOf_ReturnsCorrectIndex()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        provider.Add(message1);
        provider.Add(message2);

        // Act & Assert
        Assert.Equal(0, provider.IndexOf(message1));
        Assert.Equal(1, provider.IndexOf(message2));
        Assert.Equal(-1, provider.IndexOf(message3)); // Not in provider
    }

    [Fact]
    public void Insert_InsertsMessageAtCorrectIndex()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var insertMessage = new ChatMessage(ChatRole.User, "Inserted");
        provider.Add(message1);
        provider.Add(message2);

        // Act
        provider.Insert(1, insertMessage);

        // Assert
        Assert.Equal(3, provider.Count);
        Assert.Same(message1, provider[0]);
        Assert.Same(insertMessage, provider[1]);
        Assert.Same(message2, provider[2]);
    }

    [Fact]
    public void RemoveAt_RemovesMessageAtIndex()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        provider.Add(message1);
        provider.Add(message2);
        provider.Add(message3);

        // Act
        provider.RemoveAt(1);

        // Assert
        Assert.Equal(2, provider.Count);
        Assert.Same(message1, provider[0]);
        Assert.Same(message3, provider[1]);
    }

    [Fact]
    public void Clear_RemovesAllMessages()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider
        {
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Second")
        };

        // Act
        provider.Clear();

        // Assert
        Assert.Empty(provider);
    }

    [Fact]
    public void Contains_ReturnsTrueForExistingMessage()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);

        // Act & Assert
        Assert.Contains(message1, provider);
        Assert.DoesNotContain(message2, provider);
    }

    [Fact]
    public void CopyTo_CopiesMessagesToArray()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);
        provider.Add(message2);
        var array = new ChatMessage[4];

        // Act
        provider.CopyTo(array, 1);

        // Assert
        Assert.Null(array[0]);
        Assert.Same(message1, array[1]);
        Assert.Same(message2, array[2]);
        Assert.Null(array[3]);
    }

    [Fact]
    public void Remove_RemovesSpecificMessage()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        provider.Add(message1);
        provider.Add(message2);
        provider.Add(message3);

        // Act
        var removed = provider.Remove(message2);

        // Assert
        Assert.True(removed);
        Assert.Equal(2, provider.Count);
        Assert.Same(message1, provider[0]);
        Assert.Same(message3, provider[1]);
    }

    [Fact]
    public void Remove_ReturnsFalseForNonExistentMessage()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);

        // Act
        var removed = provider.Remove(message2);

        // Assert
        Assert.False(removed);
        Assert.Single(provider);
    }

    [Fact]
    public void GetEnumerator_Generic_ReturnsAllMessages()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);
        provider.Add(message2);

        // Act
        var messages = new List<ChatMessage>();
        messages.AddRange(provider);

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Same(message1, messages[0]);
        Assert.Same(message2, messages[1]);
    }

    [Fact]
    public void GetEnumerator_NonGeneric_ReturnsAllMessages()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        provider.Add(message1);
        provider.Add(message2);

        // Act
        var messages = new List<ChatMessage>();
        var enumerator = ((System.Collections.IEnumerable)provider).GetEnumerator();
        while (enumerator.MoveNext())
        {
            messages.Add((ChatMessage)enumerator.Current);
        }

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Same(message1, messages[0]);
        Assert.Same(message2, messages[1]);
    }

    [Fact]
    public async Task AddMessagesAsync_WithReducer_AfterMessageAdded_InvokesReducerAsync()
    {
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

        var provider = new InMemoryChatHistoryProvider(reducerMock.Object, InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded);

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, originalMessages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Single(provider);
        Assert.Equal("Reduced", provider[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task GetMessagesAsync_WithReducer_BeforeMessagesRetrieval_InvokesReducerAsync()
    {
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

        var provider = new InMemoryChatHistoryProvider(reducerMock.Object, InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval);
        // Add messages directly to the provider for this test
        foreach (var msg in originalMessages)
        {
            provider.Add(msg);
        }

        // Act
        var invokingContext = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, Array.Empty<ChatMessage>());
        var result = (await provider.InvokingAsync(invokingContext, CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Reduced", result[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.Is<List<ChatMessage>>(x => x.SequenceEqual(originalMessages)), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task AddMessagesAsync_WithReducer_ButWrongTrigger_DoesNotInvokeReducerAsync()
    {
        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        var reducerMock = new Mock<IChatReducer>();

        var provider = new InMemoryChatHistoryProvider(reducerMock.Object, InMemoryChatHistoryProvider.ChatReducerTriggerEvent.BeforeMessagesRetrieval);

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, originalMessages, []);
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Single(provider);
        Assert.Equal("Hello", provider[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task GetMessagesAsync_WithReducer_ButWrongTrigger_DoesNotInvokeReducerAsync()
    {
        // Arrange
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        var reducerMock = new Mock<IChatReducer>();

        var provider = new InMemoryChatHistoryProvider(reducerMock.Object, InMemoryChatHistoryProvider.ChatReducerTriggerEvent.AfterMessageAdded)
        {
            originalMessages[0]
        };

        // Act
        var invokingContext = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, Array.Empty<ChatMessage>());
        var result = (await provider.InvokingAsync(invokingContext, CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Hello", result[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task InvokedAsync_WithException_DoesNotAddMessagesAsync()
    {
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
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, [])
        {
            ResponseMessages = responseMessages,
            InvokeException = new InvalidOperationException("Test exception")
        };

        // Act
        await provider.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.Empty(provider);
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
