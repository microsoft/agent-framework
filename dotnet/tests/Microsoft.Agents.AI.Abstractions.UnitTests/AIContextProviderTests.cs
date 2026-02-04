// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AIContextProviderTests
{
    #region InvokingAsync Message Stamping Tests

    [Fact]
    public async Task InvokingAsync_StampsMessagesWithSourceTypeAndSourceAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithMessages();
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(typeof(TestAIContextProviderWithMessages).FullName, source);
    }

    [Fact]
    public async Task InvokingAsync_WithCustomSourceName_StampsMessagesWithCustomSourceAsync()
    {
        // Arrange
        const string CustomSourceName = "CustomContextSource";
        var provider = new TestAIContextProviderWithCustomSource(CustomSourceName);
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(CustomSourceName, source);
    }

    [Fact]
    public async Task InvokingAsync_DoesNotReStampAlreadyStampedMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithPreStampedMessages();
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, sourceType);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
        Assert.Equal(typeof(TestAIContextProviderWithPreStampedMessages).FullName, source);
    }

    [Fact]
    public async Task InvokingAsync_StampsMultipleMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithMultipleMessages();
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        List<ChatMessage> messageList = aiContext.Messages.ToList();
        Assert.Equal(3, messageList.Count);

        foreach (ChatMessage message in messageList)
        {
            Assert.NotNull(message.AdditionalProperties);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out object? sourceType));
            Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, sourceType);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSource.AdditionalPropertiesKey, out object? source));
            Assert.Equal(typeof(TestAIContextProviderWithMultipleMessages).FullName, source);
        }
    }

    [Fact]
    public async Task InvokingAsync_WithNullMessages_ReturnsContextWithoutStampingAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(aiContext.Messages);
    }

    #endregion

    #region Basic Tests

    [Fact]
    public async Task InvokedAsync_ReturnsCompletedTaskAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>([]);

        // Act
        ValueTask task = provider.InvokedAsync(new(messages));

        // Assert
        Assert.Equal(default, task);
    }

    [Fact]
    public void Serialize_ReturnsEmptyElement()
    {
        // Arrange
        var provider = new TestAIContextProvider();

        // Act
        var actual = provider.Serialize();

        // Assert
        Assert.Equal(default, actual);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!));
    }

    #endregion

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the exact context provider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the base AIContextProvider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(AIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns null when a service key is provided, even for matching types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider), "some-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => contextProvider.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<TestAIContextProvider>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    #region InvokingContext Tests

    [Fact]
    public void InvokingContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var context = new AIContextProvider.InvokingContext(messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new AIContextProvider.InvokingContext(initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var context = new AIContextProvider.InvokedContext(messages, aiContextProviderMessages: null);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new AIContextProvider.InvokedContext(initialMessages, aiContextProviderMessages: null);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokedContext_AIContextProviderMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var aiContextMessages = new List<ChatMessage> { new(ChatRole.System, "AI context message") };
        var context = new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null);

        // Act
        context.AIContextProviderMessages = aiContextMessages;

        // Assert
        Assert.Same(aiContextMessages, context.AIContextProviderMessages);
    }

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };
        var context = new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null);

        // Act
        context.ResponseMessages = responseMessages;

        // Assert
        Assert.Same(responseMessages, context.ResponseMessages);
    }

    [Fact]
    public void InvokedContext_InvokeException_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var exception = new InvalidOperationException("Test exception");
        var context = new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages: null);

        // Act
        context.InvokeException = exception;

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    #endregion

    private sealed class TestAIContextProvider : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new AIContext());
    }

    private sealed class TestAIContextProviderWithMessages : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new AIContext
            {
                Messages = [new ChatMessage(ChatRole.System, "Context Message")]
            });
    }

    private sealed class TestAIContextProviderWithCustomSource : AIContextProvider
    {
        public TestAIContextProviderWithCustomSource(string sourceName) : base(sourceName)
        {
        }

        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new AIContext
            {
                Messages = [new ChatMessage(ChatRole.System, "Context Message")]
            });
    }

    private sealed class TestAIContextProviderWithPreStampedMessages : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var message = new ChatMessage(ChatRole.System, "Pre-stamped Message");
            message.AdditionalProperties = new AdditionalPropertiesDictionary
            {
                [AgentRequestMessageSourceType.AdditionalPropertiesKey] = AgentRequestMessageSourceType.AIContextProvider,
                [AgentRequestMessageSource.AdditionalPropertiesKey] = this.GetType().FullName!
            };
            return new(new AIContext
            {
                Messages = [message]
            });
        }
    }

    private sealed class TestAIContextProviderWithMultipleMessages : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new AIContext
            {
                Messages = [
                    new ChatMessage(ChatRole.System, "Message 1"),
                    new ChatMessage(ChatRole.User, "Message 2"),
                    new ChatMessage(ChatRole.Assistant, "Message 3")
                ]
            });
    }
}
