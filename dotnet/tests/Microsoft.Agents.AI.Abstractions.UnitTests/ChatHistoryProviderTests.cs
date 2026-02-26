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

    #region InvokingAsync / InvokedAsync Null Check Tests

    [Fact]
    public async Task InvokingAsync_NullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokingAsync(null!).AsTask());
    }

    [Fact]
    public async Task InvokedAsync_NullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokedAsync(null!).AsTask());
    }

    #endregion

    #region InvokingCoreAsync Tests

    [Fact]
    public async Task InvokingCoreAsync_CallsProvideChatHistoryAndReturnsMessagesAsync()
    {
        // Arrange
        var historyMessages = new[] { new ChatMessage(ChatRole.User, "History message") };
        var provider = new TestChatHistoryProvider(provideMessages: historyMessages);
        var requestMessages = new[] { new ChatMessage(ChatRole.User, "Request message") };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, requestMessages);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("History message", result[0].Text);
        Assert.Equal("Request message", result[1].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_HistoryAppearsBeforeRequestMessagesAsync()
    {
        // Arrange
        var historyMessages = new[]
        {
            new ChatMessage(ChatRole.User, "Hist1"),
            new ChatMessage(ChatRole.Assistant, "Hist2")
        };
        var provider = new TestChatHistoryProvider(provideMessages: historyMessages);
        var requestMessages = new[] { new ChatMessage(ChatRole.User, "Req1") };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, requestMessages);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Equal("Hist1", result[0].Text);
        Assert.Equal("Hist2", result[1].Text);
        Assert.Equal("Req1", result[2].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_StampsHistoryMessagesWithChatHistorySourceAsync()
    {
        // Arrange
        var historyMessages = new[] { new ChatMessage(ChatRole.User, "History") };
        var provider = new TestChatHistoryProvider(provideMessages: historyMessages);
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, []);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result[0].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task InvokingCoreAsync_NoFilterAppliedWhenProvideOutputFilterIsNullAsync()
    {
        // Arrange
        var historyMessages = new[]
        {
            new ChatMessage(ChatRole.User, "User msg"),
            new ChatMessage(ChatRole.System, "System msg"),
            new ChatMessage(ChatRole.Assistant, "Assistant msg")
        };
        var provider = new TestChatHistoryProvider(provideMessages: historyMessages);
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, []);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - all 3 history messages returned (no filter)
        Assert.Equal(3, result.Count);
    }

    [Fact]
    public async Task InvokingCoreAsync_AppliesProvideOutputFilterWhenProvidedAsync()
    {
        // Arrange
        var historyMessages = new[]
        {
            new ChatMessage(ChatRole.User, "User msg"),
            new ChatMessage(ChatRole.System, "System msg"),
            new ChatMessage(ChatRole.Assistant, "Assistant msg")
        };
        var provider = new TestChatHistoryProvider(
            provideMessages: historyMessages,
            provideOutputMessageFilter: msgs => msgs.Where(m => m.Role == ChatRole.User));
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, []);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - only User messages remain after filter
        Assert.Single(result);
        Assert.Equal("User msg", result[0].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_ReturnsEmptyHistoryByDefaultAsync()
    {
        // Arrange - provider that doesn't override ProvideChatHistoryAsync (uses base default)
        var provider = new DefaultChatHistoryProvider();
        var requestMessages = new[] { new ChatMessage(ChatRole.User, "Hello") };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, requestMessages);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - only the request message (no history)
        Assert.Single(result);
        Assert.Equal("Hello", result[0].Text);
    }

    #endregion

    #region InvokedCoreAsync Tests

    [Fact]
    public async Task InvokedCoreAsync_CallsStoreChatHistoryWithFilteredMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var externalMessage = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMessage = new ChatMessage(ChatRole.User, "From history")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "source");
        var responseMessages = new[] { new ChatMessage(ChatRole.Assistant, "Response") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, new[] { externalMessage, chatHistoryMessage }, responseMessages);

        // Act
        await provider.InvokedAsync(context);

        // Assert - default filter excludes ChatHistory-sourced messages
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Single(storedRequest);
        Assert.Equal("External", storedRequest[0].Text);
        Assert.Same(responseMessages, provider.LastStoredContext.ResponseMessages);
    }

    [Fact]
    public async Task InvokedCoreAsync_SkipsStorageWhenInvokeExceptionIsNotNullAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "msg")], new InvalidOperationException("Failed"));

        // Act
        await provider.InvokedAsync(context);

        // Assert - StoreChatHistoryAsync was NOT called
        Assert.Null(provider.LastStoredContext);
    }

    [Fact]
    public async Task InvokedCoreAsync_UsesCustomStoreInputFilterAsync()
    {
        // Arrange - filter that only keeps System messages
        var provider = new TestChatHistoryProvider(
            storeInputMessageFilter: msgs => msgs.Where(m => m.Role == ChatRole.System));
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "User msg"),
            new ChatMessage(ChatRole.System, "System msg")
        };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, messages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(context);

        // Assert - only System messages were passed to store
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Single(storedRequest);
        Assert.Equal("System msg", storedRequest[0].Text);
    }

    [Fact]
    public async Task InvokedCoreAsync_DefaultFilterExcludesChatHistorySourcedMessagesAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var external = new ChatMessage(ChatRole.User, "External");
        var fromHistory = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var fromContext = new ChatMessage(ChatRole.User, "Context")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "src");
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, [external, fromHistory, fromContext], []);

        // Act
        await provider.InvokedAsync(context);

        // Assert - External and AIContextProvider messages kept, ChatHistory excluded
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Equal(2, storedRequest.Count);
        Assert.Equal("External", storedRequest[0].Text);
        Assert.Equal("Context", storedRequest[1].Text);
    }

    [Fact]
    public async Task InvokedCoreAsync_PassesResponseMessagesToStoreAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider();
        var responseMessages = new[] { new ChatMessage(ChatRole.Assistant, "Resp1"), new ChatMessage(ChatRole.Assistant, "Resp2") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "msg")], responseMessages);

        // Act
        await provider.InvokedAsync(context);

        // Assert
        Assert.NotNull(provider.LastStoredContext);
        Assert.Same(responseMessages, provider.LastStoredContext!.ResponseMessages);
    }

    #endregion

    private sealed class TestChatHistoryProvider : ChatHistoryProvider
    {
        private readonly IEnumerable<ChatMessage>? _provideMessages;

        public InvokedContext? LastStoredContext { get; private set; }

        public TestChatHistoryProvider(
            IEnumerable<ChatMessage>? provideMessages = null,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
            : base(provideOutputMessageFilter, storeInputMessageFilter)
        {
            this._provideMessages = provideMessages;
        }

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(this._provideMessages ?? []);

        protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.LastStoredContext = context;
            return default;
        }
    }

    /// <summary>
    /// A provider that uses only base class defaults (no overrides of ProvideChatHistoryAsync/StoreChatHistoryAsync).
    /// </summary>
    private sealed class DefaultChatHistoryProvider : ChatHistoryProvider;
}
