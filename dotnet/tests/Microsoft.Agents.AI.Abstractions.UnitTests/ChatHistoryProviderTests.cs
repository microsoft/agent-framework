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
/// Contains tests for the <see cref="ChatHistoryProvider"/> class.
/// </summary>
public class ChatHistoryProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

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
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, null!, []));
    }

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, responseMessages);

        // Assert
        Assert.Same(responseMessages, context.ResponseMessages);
    }

    [Fact]
    public void InvokedContext_InvokeException_Roundtrips()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var exception = new InvalidOperationException("Test exception");

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, exception);

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    [Fact]
    public void InvokedContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokedContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokedContext_Session_CanBeNull()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, null, requestMessages, []);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(null!, s_mockSession, requestMessages, []));
    }

    [Fact]
    public void InvokedContext_SuccessConstructor_ThrowsForNullResponseMessages()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (IEnumerable<ChatMessage>)null!));
    }

    [Fact]
    public void InvokedContext_FailureConstructor_ThrowsForNullException()
    {
        // Arrange
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (Exception)null!));
    }

    #endregion

    private sealed class TestChatHistoryProvider : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new ChatMessage[] { new(ChatRole.User, "Test Message") }.Concat(context.RequestMessages));

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;
    }
}
