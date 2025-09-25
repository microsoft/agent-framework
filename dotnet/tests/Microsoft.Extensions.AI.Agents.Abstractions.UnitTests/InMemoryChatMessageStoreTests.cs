// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="InMemoryChatMessageStore"/> class.
/// </summary>
public class InMemoryChatMessageStoreTests
{
    [Fact]
    public void Constructor_Throws_ForNullReducer() =>
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new InMemoryChatMessageStore(null!));

    [Fact]
    public void Constructor_DefaultsToBeforeMessageRetrieval_ForNotProvidedTriggerEvent()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var store = new InMemoryChatMessageStore(reducerMock.Object);

        // Assert
        Assert.Equal(InMemoryChatMessageStore.ChatReducerTriggerEvent.BeforeMessagesRetrieval, store.ReducerTriggerEvent);
    }

    [Fact]
    public void Constructor_Arguments_SetOnPropertiesCorrectly()
    {
        // Arrange & Act
        var reducerMock = new Mock<IChatReducer>();
        var store = new InMemoryChatMessageStore(reducerMock.Object, InMemoryChatMessageStore.ChatReducerTriggerEvent.AfterMessageAdded);

        // Assert
        Assert.Same(reducerMock.Object, store.ChatReducer);
        Assert.Equal(InMemoryChatMessageStore.ChatReducerTriggerEvent.AfterMessageAdded, store.ReducerTriggerEvent);
    }

    [Fact]
    public async Task AddMessagesAsyncAddsMessagesAndReturnsNullThreadIdAsync()
    {
        var store = new InMemoryChatMessageStore();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        await store.AddMessagesAsync(messages, CancellationToken.None);

        Assert.Equal(2, store.Count);
        Assert.Equal("Hello", store[0].Text);
        Assert.Equal("Hi there!", store[1].Text);
    }

    [Fact]
    public async Task AddMessagesAsyncWithEmptyDoesNotFailAsync()
    {
        var store = new InMemoryChatMessageStore();

        await store.AddMessagesAsync([], CancellationToken.None);

        Assert.Empty(store);
    }

    [Fact]
    public async Task GetMessagesAsyncReturnsAllMessagesAsync()
    {
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "Test1"),
            new ChatMessage(ChatRole.Assistant, "Test2")
        };

        var result = (await store.GetMessagesAsync(CancellationToken.None)).ToList();

        Assert.Equal(2, result.Count);
        Assert.Contains(result, m => m.Text == "Test1");
        Assert.Contains(result, m => m.Text == "Test2");
    }

    [Fact]
    public async Task DeserializeConstructorWithEmptyElementAsync()
    {
        var emptyObject = JsonSerializer.Deserialize("{}", TestJsonSerializerContext.Default.JsonElement);

        var newStore = new InMemoryChatMessageStore(emptyObject);

        Assert.Empty(newStore);
    }

    [Fact]
    public async Task SerializeAndDeserializeConstructorRoundtripsAsync()
    {
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B")
        };

        var jsonElement = await store.SerializeStateAsync();
        var newStore = new InMemoryChatMessageStore(jsonElement.Value);

        Assert.Equal(2, newStore.Count);
        Assert.Equal("A", newStore[0].Text);
        Assert.Equal("B", newStore[1].Text);
    }

    [Fact]
    public async Task AddMessagesAsyncWithEmptyMessagesDoesNotChangeStoreAsync()
    {
        var store = new InMemoryChatMessageStore();
        var messages = new List<ChatMessage>();

        await store.AddMessagesAsync(messages, CancellationToken.None);

        Assert.Empty(store);
    }

    [Fact]
    public async Task AddMessagesAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => store.AddMessagesAsync(null!, CancellationToken.None));
    }

    [Fact]
    public void DeserializeContructor_WithNullSerializedState_CreatesEmptyStore()
    {
        // Act
        var store = new InMemoryChatMessageStore(new JsonElement());

        // Assert
        Assert.Empty(store);
    }

    [Fact]
    public async Task DeserializeContructor_WithEmptyMessages_DoesNotAddMessagesAsync()
    {
        // Arrange
        var stateWithEmptyMessages = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["messages"] = new List<ChatMessage>() },
            TestJsonSerializerContext.Default.IDictionaryStringObject);

        // Act
        var store = new InMemoryChatMessageStore(stateWithEmptyMessages);

        // Assert
        Assert.Empty(store);
    }

    [Fact]
    public async Task DeserializeConstructor_WithNullMessages_DoesNotAddMessagesAsync()
    {
        // Arrange
        var stateWithNullMessages = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["messages"] = null! },
            TestJsonSerializerContext.Default.DictionaryStringObject);

        // Act
        var store = new InMemoryChatMessageStore(stateWithNullMessages);

        // Assert
        Assert.Empty(store);
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
        var store = new InMemoryChatMessageStore(serializedState);

        // Assert
        Assert.Equal(2, store.Count);
        Assert.Equal("User message", store[0].Text);
        Assert.Equal("Assistant message", store[1].Text);
    }

    [Fact]
    public void IndexerGet_ReturnsCorrectMessage()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);
        store.Add(message2);

        // Act & Assert
        Assert.Same(message1, store[0]);
        Assert.Same(message2, store[1]);
    }

    [Fact]
    public void IndexerSet_UpdatesMessage()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var originalMessage = new ChatMessage(ChatRole.User, "Original");
        var newMessage = new ChatMessage(ChatRole.User, "Updated");
        store.Add(originalMessage);

        // Act
        store[0] = newMessage;

        // Assert
        Assert.Same(newMessage, store[0]);
        Assert.Equal("Updated", store[0].Text);
    }

    [Fact]
    public void IsReadOnly_ReturnsFalse()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();

        // Act & Assert
        Assert.False(store.IsReadOnly);
    }

    [Fact]
    public void IndexOf_ReturnsCorrectIndex()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        store.Add(message1);
        store.Add(message2);

        // Act & Assert
        Assert.Equal(0, store.IndexOf(message1));
        Assert.Equal(1, store.IndexOf(message2));
        Assert.Equal(-1, store.IndexOf(message3)); // Not in store
    }

    [Fact]
    public void Insert_InsertsMessageAtCorrectIndex()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var insertMessage = new ChatMessage(ChatRole.User, "Inserted");
        store.Add(message1);
        store.Add(message2);

        // Act
        store.Insert(1, insertMessage);

        // Assert
        Assert.Equal(3, store.Count);
        Assert.Same(message1, store[0]);
        Assert.Same(insertMessage, store[1]);
        Assert.Same(message2, store[2]);
    }

    [Fact]
    public void RemoveAt_RemovesMessageAtIndex()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        store.Add(message1);
        store.Add(message2);
        store.Add(message3);

        // Act
        store.RemoveAt(1);

        // Assert
        Assert.Equal(2, store.Count);
        Assert.Same(message1, store[0]);
        Assert.Same(message3, store[1]);
    }

    [Fact]
    public void Clear_RemovesAllMessages()
    {
        // Arrange
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Second")
        };

        // Act
        store.Clear();

        // Assert
        Assert.Empty(store);
    }

    [Fact]
    public void Contains_ReturnsTrueForExistingMessage()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);

        // Act & Assert
        Assert.Contains(message1, store);
        Assert.DoesNotContain(message2, store);
    }

    [Fact]
    public void CopyTo_CopiesMessagesToArray()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);
        store.Add(message2);
        var array = new ChatMessage[4];

        // Act
        store.CopyTo(array, 1);

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
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        var message3 = new ChatMessage(ChatRole.User, "Third");
        store.Add(message1);
        store.Add(message2);
        store.Add(message3);

        // Act
        var removed = store.Remove(message2);

        // Assert
        Assert.True(removed);
        Assert.Equal(2, store.Count);
        Assert.Same(message1, store[0]);
        Assert.Same(message3, store[1]);
    }

    [Fact]
    public void Remove_ReturnsFalseForNonExistentMessage()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);

        // Act
        var removed = store.Remove(message2);

        // Assert
        Assert.False(removed);
        Assert.Single(store);
    }

    [Fact]
    public void GetEnumerator_Generic_ReturnsAllMessages()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);
        store.Add(message2);

        // Act
        var messages = new List<ChatMessage>();
        messages.AddRange(store);

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Same(message1, messages[0]);
        Assert.Same(message2, messages[1]);
    }

    [Fact]
    public void GetEnumerator_NonGeneric_ReturnsAllMessages()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var message1 = new ChatMessage(ChatRole.User, "First");
        var message2 = new ChatMessage(ChatRole.Assistant, "Second");
        store.Add(message1);
        store.Add(message2);

        // Act
        var messages = new List<ChatMessage>();
        var enumerator = ((System.Collections.IEnumerable)store).GetEnumerator();
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

        var store = new InMemoryChatMessageStore(reducerMock.Object, InMemoryChatMessageStore.ChatReducerTriggerEvent.AfterMessageAdded);

        // Act
        await store.AddMessagesAsync(originalMessages, CancellationToken.None);

        // Assert
        Assert.Single(store);
        Assert.Equal("Reduced", store[0].Text);
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

        var store = new InMemoryChatMessageStore(reducerMock.Object, InMemoryChatMessageStore.ChatReducerTriggerEvent.BeforeMessagesRetrieval);
        await store.AddMessagesAsync(originalMessages, CancellationToken.None);

        // Act
        var result = (await store.GetMessagesAsync(CancellationToken.None)).ToList();

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

        var store = new InMemoryChatMessageStore(reducerMock.Object, InMemoryChatMessageStore.ChatReducerTriggerEvent.BeforeMessagesRetrieval);

        // Act
        await store.AddMessagesAsync(originalMessages, CancellationToken.None);

        // Assert
        Assert.Single(store);
        Assert.Equal("Hello", store[0].Text);
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

        var store = new InMemoryChatMessageStore(reducerMock.Object, InMemoryChatMessageStore.ChatReducerTriggerEvent.AfterMessageAdded)
        {
            originalMessages[0]
        };

        // Act
        var result = (await store.GetMessagesAsync(CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Hello", result[0].Text);
        reducerMock.Verify(r => r.ReduceAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Never);
    }
}
