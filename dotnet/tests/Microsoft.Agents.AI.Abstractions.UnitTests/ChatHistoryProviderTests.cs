// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProvider"/> class.
/// </summary>
public class ChatHistoryProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region InvokingAsync Message Stamping Tests

    [Fact]
    public async Task InvokingAsync_StampsMessagesWithSourceTypeAndSourceIdAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, typedAttribution.SourceType);
        Assert.Equal(typeof(TestChatHistoryProvider).FullName, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_WithCustomSourceId_StampsMessagesWithCustomSourceIdAsync()
    {
        // Arrange
        const string CustomSourceId = "CustomHistorySource";
        var provider = new TestChatHistoryProviderWithCustomSource(CustomSourceId);
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, typedAttribution.SourceType);
        Assert.Equal(CustomSourceId, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_DoesNotReStampAlreadyStampedMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProviderWithPreStampedMessages();
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        ChatMessage message = messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, typedAttribution.SourceType);
        Assert.Equal(typeof(TestChatHistoryProviderWithPreStampedMessages).FullName, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_StampsMultipleMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProviderWithMultipleMessages();
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        IEnumerable<ChatMessage> messages = await provider.InvokingAsync(context);

        // Assert
        List<ChatMessage> messageList = messages.ToList();
        Assert.Equal(3, messageList.Count);

        foreach (ChatMessage message in messageList)
        {
            Assert.NotNull(message.AdditionalProperties);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
            var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
            Assert.Equal(AgentRequestMessageSourceType.ChatHistory, typedAttribution.SourceType);
            Assert.Equal(typeof(TestChatHistoryProviderWithMultipleMessages).FullName, typedAttribution.SourceId);
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
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokingContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokingContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokingContext_Session_CanBeNull()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, null, messages);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokingContext(null!, s_mockSession, messages));
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullRequestMessages()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

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
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Act
        context.InvokeException = exception;

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    [Fact]
    public void InvokedContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokedContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokedContext_Session_CanBeNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, null, requestMessages);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(null!, s_mockSession, requestMessages));
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
        public TestChatHistoryProviderWithCustomSource(string sourceId) : base(sourceId)
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
                [AgentRequestMessageSourceAttribution.AdditionalPropertiesKey] = new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, this.GetType().FullName!)
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
