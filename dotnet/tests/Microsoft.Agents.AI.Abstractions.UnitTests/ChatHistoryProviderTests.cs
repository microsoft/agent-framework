// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProvider"/> class.
/// </summary>
public class ChatHistoryProviderTests
{
    #region InvokingAsync Message Stamping Tests

    [Fact]
    public async Task InvokingAsync_StampsMessagesWithSourceTypeAndSourceAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var context = new ChatHistoryProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(typeof(TestChatHistoryProvider).FullName, source);
    }

    [Fact]
    public async Task InvokingAsync_WithCustomSourceName_StampsMessagesWithCustomSourceAsync()
    {
        // Arrange
        const string CustomSourceName = "CustomHistorySource";
        var provider = new TestChatHistoryProviderWithCustomSource(CustomSourceName);
        var context = new ChatHistoryProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(CustomSourceName, source);
    }

    [Fact]
    public async Task InvokingAsync_DoesNotReStampAlreadyStampedMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProviderWithPreStampedMessages();
        var context = new ChatHistoryProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(typeof(TestChatHistoryProviderWithPreStampedMessages).FullName, source);
    }

    [Fact]
    public async Task InvokingAsync_StampsMultipleMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProviderWithMultipleMessages();
        var context = new ChatHistoryProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        List<ChatMessage> messageList = messages.ToList();
        Assert.Equal(3, messageList.Count);

        foreach (ChatMessage message in messageList)
        {
            Assert.NotNull(message.AdditionalProperties);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
            Assert.Equal(AgentRequestMessageSourceType.ChatHistory, sourceType);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
            Assert.Equal(typeof(TestChatHistoryProviderWithMultipleMessages).FullName, source);
        }
    }

    #endregion

    #region GetService Method Tests

    [Fact]
    public void GetService_RequestingExactProviderType_ReturnsProvider()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(TestChatHistoryProvider));
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_RequestingBaseProviderType_ReturnsProvider()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(ChatHistoryProvider));
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(string));
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService(typeof(TestChatHistoryProvider), "some-key");
        Assert.Null(result);
    }

    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        var provider = new TestChatHistoryProvider();
        Assert.Throws<ArgumentNullException>(() => provider.GetService(null!));
    }

    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService<TestChatHistoryProvider>();
        Assert.NotNull(result);
        Assert.Same(provider, result);
    }

    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        var provider = new TestChatHistoryProvider();
        var result = provider.GetService<string>();
        Assert.Null(result);
    }

    #endregion

    #region InvokingContext Tests

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokingContext(null!));
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatHistoryProvider.InvokingContext(messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatHistoryProvider.InvokingContext(initialMessages);

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
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(null!, []));
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatHistoryProvider.InvokedContext(requestMessages, []);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatHistoryProvider.InvokedContext(initialMessages, []);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokedContext_ChatHistoryProviderMessages_SetterRoundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newProviderMessages = new List<ChatMessage> { new(ChatRole.System, "System message") };
        var context = new ChatHistoryProvider.InvokedContext(requestMessages, []);

        // Act
        context.ChatHistoryProviderMessages = newProviderMessages;

        // Assert
        Assert.Same(newProviderMessages, context.ChatHistoryProviderMessages);
    }

    [Fact]
    public void InvokedContext_AIContextProviderMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var aiContextMessages = new List<ChatMessage> { new(ChatRole.System, "AI context message") };
        var context = new ChatHistoryProvider.InvokedContext(requestMessages, []);

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
        var context = new ChatHistoryProvider.InvokedContext(requestMessages, []);

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
        var context = new ChatHistoryProvider.InvokedContext(requestMessages, []);

        // Act
        context.InvokeException = exception;

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    #endregion

    private sealed class TestChatHistoryProvider : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new([new ChatMessage(ChatRole.User, "Test Message")]);

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }

    private sealed class TestChatHistoryProviderWithCustomSource : ChatHistoryProvider
    {
        public TestChatHistoryProviderWithCustomSource(string sourceName) : base(sourceName)
        {
        }

        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new([new ChatMessage(ChatRole.User, "Test Message")]);

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }

    private sealed class TestChatHistoryProviderWithPreStampedMessages : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var message = new ChatMessage(ChatRole.User, "Pre-stamped Message");
            message.AdditionalProperties = new AdditionalPropertiesDictionary
            {
                [AgentRequestMessageSourceType.AdditionalPropertiesKey] = AgentRequestMessageSourceType.ChatHistory,
                [AgentRequestMessageSource.AdditionalPropertiesKey] = this.GetType().FullName!
            };
            return new([message]);
        }

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }

    private sealed class TestChatHistoryProviderWithMultipleMessages : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new([
                new ChatMessage(ChatRole.User, "Message 1"),
                new ChatMessage(ChatRole.Assistant, "Message 2"),
                new ChatMessage(ChatRole.User, "Message 3")
            ]);

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => default;
    }
}
