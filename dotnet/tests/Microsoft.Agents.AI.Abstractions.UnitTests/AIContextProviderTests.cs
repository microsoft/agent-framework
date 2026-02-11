// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AIContextProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region InvokingAsync Message Stamping Tests

    [Fact]
    public async Task InvokingAsync_StampsMessagesWithSourceTypeAndSourceIdAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithMessages();
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, typedAttribution.SourceType);
        Assert.Equal(typeof(TestAIContextProviderWithMessages).FullName, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_WithCustomSourceId_StampsMessagesWithCustomSourceIdAsync()
    {
        // Arrange
        const string CustomSourceId = "CustomContextSource";
        var provider = new TestAIContextProviderWithCustomSource(CustomSourceId);
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, typedAttribution.SourceType);
        Assert.Equal(CustomSourceId, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_DoesNotReStampAlreadyStampedMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithPreStampedMessages();
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        ChatMessage message = aiContext.Messages.Single();
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
        var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, typedAttribution.SourceType);
        Assert.Equal(typeof(TestAIContextProviderWithPreStampedMessages).FullName, typedAttribution.SourceId);
    }

    [Fact]
    public async Task InvokingAsync_StampsMultipleMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProviderWithMultipleMessages();
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

        // Act
        AIContext aiContext = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(aiContext.Messages);
        List<ChatMessage> messageList = aiContext.Messages.ToList();
        Assert.Equal(3, messageList.Count);

        foreach (ChatMessage message in messageList)
        {
            Assert.NotNull(message.AdditionalProperties);
            Assert.True(message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out object? attribution));
            var typedAttribution = Assert.IsType<AgentRequestMessageSourceAttribution>(attribution);
            Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, typedAttribution.SourceType);
            Assert.Equal(typeof(TestAIContextProviderWithMultipleMessages).FullName, typedAttribution.SourceId);
        }
    }

    [Fact]
    public async Task InvokingAsync_WithNullMessages_ReturnsContextWithoutStampingAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Request")]);

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
        ValueTask task = provider.InvokedAsync(new(s_mockAgent, s_mockSession, messages));

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
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, null!));
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
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokingContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokingContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokingContext_Session_CanBeNull()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, null, messages);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!, s_mockSession, messages));
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var messages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, messages);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokedContext_RequestMessages_SetterRoundtrips()
    {
        // Arrange
        var initialMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "New message") };
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, initialMessages);

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

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
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Act
        context.InvokeException = exception;

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    [Fact]
    public void InvokedContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokedContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokedContext_Session_CanBeNull()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, null, requestMessages);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!, s_mockSession, requestMessages));
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
        public TestAIContextProviderWithCustomSource(string sourceId) : base(sourceId)
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
                [AgentRequestMessageSourceAttribution.AdditionalPropertiesKey] = new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, this.GetType().FullName!)
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
