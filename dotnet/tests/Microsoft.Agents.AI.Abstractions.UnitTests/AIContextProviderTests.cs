// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AIContextProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region Basic Tests

    [Fact]
    public async Task InvokedAsync_ReturnsCompletedTaskAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>([]);

        // Act
        ValueTask task = provider.InvokedAsync(new(s_mockAgent, s_mockSession, messages, []));

        // Assert
        Assert.Equal(default, task);
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
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, null!, []));
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
    public void InvokingContext_Constructor_ThrowsForNullAIContext()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokingContext_AIContext_ConstructorValueRoundtrips()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(aiContext, context.AIContext);
    }

    [Fact]
    public void InvokingContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokingContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokingContext_Session_CanBeNull()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, null, aiContext);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!, s_mockSession, aiContext));
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, responseMessages);

        // Assert
        Assert.Same(responseMessages, context.ResponseMessages);
    }

    [Fact]
    public void InvokedContext_InvokeException_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var exception = new InvalidOperationException("Test exception");

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, exception);

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    [Fact]
    public void InvokedContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokedContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokedContext_Session_CanBeNull()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, null, requestMessages, []);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!, s_mockSession, requestMessages, []));
    }

    [Fact]
    public void InvokedContext_SuccessConstructor_ThrowsForNullResponseMessages()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (IEnumerable<ChatMessage>)null!));
    }

    [Fact]
    public void InvokedContext_FailureConstructor_ThrowsForNullException()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (Exception)null!));
    }

    #endregion

    private sealed class TestAIContextProvider : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(new AIContext());
    }
}
