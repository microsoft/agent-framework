// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatMessageStore"/> class.
/// </summary>
public class ChatMessageStoreTests
{
    #region GetService Method Tests

    [Fact]
    public void GetService_RequestingExactStoreType_ReturnsStore()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(TestChatMessageStore));
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_RequestingBaseStoreType_ReturnsStore()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(ChatMessageStore));
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(string));
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService(typeof(TestChatMessageStore), "some-key");
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        var store = new TestChatMessageStore();
        Assert.Throws<ArgumentNullException>(() => store.GetService(null!));
    }

    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService<TestChatMessageStore>();
        Assert.NotNull(result);
        Assert.Same(store, result);
    }

    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        var store = new TestChatMessageStore();
        var result = store.GetService<string>();
        Assert.Null(result);
    }

    #endregion

    #region InvokingContext Tests

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatMessageStore.InvokingContext(null!));
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatMessageStore.InvokingContext(messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatMessageStore.InvokingContext(initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullRequestMessages()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatMessageStore.InvokedContext(null!, []));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullChatMessageStoreMessages()
    {
        // Arrange & Act & Assert
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        Assert.Throws<ArgumentNullException>(() => new ChatMessageStore.InvokedContext(messages, null!));
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatMessageStore.InvokedContext(initialMessages, []);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokedContext_ChatMessageStoreMessages_SetterThrowsForNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.ChatMessageStoreMessages = null!);
    }

    [Fact]
    public void InvokedContext_ChatMessageStoreMessages_SetterRoundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newStoreMessages = new List<ChatMessage> { new(ChatRole.System, "System message") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act
        context.ChatMessageStoreMessages = newStoreMessages;

        // Assert
        Assert.Same(newStoreMessages, context.ChatMessageStoreMessages);
    }

    [Fact]
    public void InvokedContext_AIContextProviderMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var aiContextMessages = new List<ChatMessage> { new(ChatRole.System, "AI context message") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act
        context.AIContextProviderMessages = aiContextMessages;

        // Assert
        Assert.Same(aiContextMessages, context.AIContextProviderMessages);
    }

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act
        context.ResponseMessages = responseMessages;

        // Assert
        Assert.Same(responseMessages, context.ResponseMessages);
    }

    [Fact]
    public void InvokedContext_InvokeException_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var exception = new InvalidOperationException("Test exception");
        var context = new ChatMessageStore.InvokedContext(requestMessages, []);

        // Act
        context.InvokeException = exception;

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    #endregion

    private sealed class TestChatMessageStore : ChatMessageStore
    {
        public override ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(Array.Empty<ChatMessage>());

        public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }
}
