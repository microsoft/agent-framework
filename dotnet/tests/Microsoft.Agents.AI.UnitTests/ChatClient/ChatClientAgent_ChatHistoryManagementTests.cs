// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests that verify the chat history management functionality of the <see cref="ChatClientAgent"/> class,
/// e.g. that it correctly reads and updates chat history in any available <see cref="ChatHistoryProvider"/> or that
/// it uses conversation id correctly for service managed chat history.
/// </summary>
public class ChatClientAgent_ChatHistoryManagementTests
{
    #region ConversationId Tests

    /// <summary>
    /// Verify that RunAsync does not throw when providing a ConversationId via both AgentSession and
    /// via ChatOptions and the two are the same.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotThrow_WhenSpecifyingTwoSameConversationIdsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { ConversationId = "ConvId" };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.ConversationId == "ConvId"),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentSession? session = new() { ConversationId = "ConvId" };

        // Act & Assert
        var response = await agent.RunAsync([new(ChatRole.User, "test")], session, options: new ChatClientAgentRunOptions(chatOptions));
        Assert.NotNull(response);
    }

    /// <summary>
    /// Verify that RunAsync throws when providing a ConversationId via both AgentSession and
    /// via ChatOptions and the two are different.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenSpecifyingTwoDifferentConversationIdsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { ConversationId = "ConvId" };
        Mock<IChatClient> mockService = new();

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentSession? session = new() { ConversationId = "ThreadId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session, options: new ChatClientAgentRunOptions(chatOptions)));
    }

    /// <summary>
    /// Verify that RunAsync clones the ChatOptions when providing a session with a ConversationId and a ChatOptions.
    /// </summary>
    [Fact]
    public async Task RunAsync_ClonesChatOptions_ToAddConversationIdAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100 && opts.ConversationId == "ConvId"),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentSession? session = new() { ConversationId = "ConvId" };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], session, options: new ChatClientAgentRunOptions(chatOptions));

        // Assert
        Assert.Null(chatOptions.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync throws if a session is provided that uses a conversation id already, but the service does not return one on invoke.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_ForMissingConversationIdWithConversationIdSessionAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentSession? session = new() { ConversationId = "ConvId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));
    }

    /// <summary>
    /// Verify that RunAsync sets the ConversationId on the session when the service returns one.
    /// </summary>
    [Fact]
    public async Task RunAsync_SetsConversationIdOnSession_WhenReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });
        ChatClientAgentSession? session = new();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.Equal("ConvId", session.ConversationId);
    }

    #endregion

    #region ChatHistoryProvider Tests

    /// <summary>
    /// Verify that RunAsync uses the default InMemoryChatHistoryProvider when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesDefaultInMemoryChatHistoryProvider_WhenNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        var inMemoryProvider = agent.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(inMemoryProvider);
        var messages = inMemoryProvider.GetMessages(session!);
        Assert.Equal(2, messages.Count);
        Assert.Equal("test", messages[0].Text);
        Assert.Equal("response", messages[1].Text);
    }

    /// <summary>
    /// Verify that RunAsync uses the ChatHistoryProvider when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesChatHistoryProvider_WhenProvidedAndNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(new List<ChatMessage> { new(ChatRole.User, "Existing Chat History") }.Concat(ctx.RequestMessages).ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = mockChatHistoryProvider.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.Same(mockChatHistoryProvider.Object, agent.ChatHistoryProvider);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokingContext>(x => x.RequestMessages.Count() == 1),
                ItExpr.IsAny<CancellationToken>());
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 2 && x.ResponseMessages!.Count() == 1),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync notifies the ChatHistoryProvider on failure.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesChatHistoryProvider_OnFailureAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Throws(new InvalidOperationException("Test Error"));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = mockChatHistoryProvider.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert
        Assert.Same(mockChatHistoryProvider.Object, agent.ChatHistoryProvider);
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ResponseMessages == null && x.InvokeException!.Message == "Test Error"),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync throws when a ChatHistoryProvider is provided and the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenChatHistoryProviderProvidedAndConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = new InMemoryChatHistoryProvider()
        });

        // Act & Assert
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));
        Assert.Equal("Only ConversationId or ChatHistoryProvider may be used, but not both. The service returned a conversation id indicating server-side chat history management, but the agent has a ChatHistoryProvider configured.", exception.Message);
    }

    /// <summary>
    /// Verify that RunAsync clears the ChatHistoryProvider when ThrowOnChatHistoryProviderConflict is false
    /// and ClearOnChatHistoryProviderConflict is true.
    /// </summary>
    [Fact]
    public async Task RunAsync_ClearsChatHistoryProvider_WhenThrowDisabledAndClearEnabledAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = new InMemoryChatHistoryProvider(),
            ThrowOnChatHistoryProviderConflict = false,
            ClearOnChatHistoryProviderConflict = true,
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.Null(agent.ChatHistoryProvider);
        Assert.Equal("ConvId", session!.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync does not throw and does not clear the ChatHistoryProvider when both
    /// ThrowOnChatHistoryProviderConflict and ClearOnChatHistoryProviderConflict are false.
    /// </summary>
    [Fact]
    public async Task RunAsync_KeepsChatHistoryProvider_WhenThrowAndClearDisabledAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        var chatHistoryProvider = new InMemoryChatHistoryProvider();
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = chatHistoryProvider,
            ThrowOnChatHistoryProviderConflict = false,
            ClearOnChatHistoryProviderConflict = false,
            WarnOnChatHistoryProviderConflict = false,
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.Same(chatHistoryProvider, agent.ChatHistoryProvider);
        Assert.Equal("ConvId", session!.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync still throws when ThrowOnChatHistoryProviderConflict is true
    /// even if ClearOnChatHistoryProviderConflict is also true (throw takes precedence).
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenThrowEnabledRegardlessOfClearSettingAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = new InMemoryChatHistoryProvider(),
            ThrowOnChatHistoryProviderConflict = true,
            ClearOnChatHistoryProviderConflict = true,
        });

        // Act & Assert
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));
    }

    /// <summary>
    /// Verify that RunAsync does not throw when no ChatHistoryProvider is configured on options,
    /// even if the service returns a conversation id (default InMemoryChatHistoryProvider is used but not from options).
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotThrow_WhenNoChatHistoryProviderInOptionsAndConversationIdReturnedAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert - no exception, session gets the conversation id
        Assert.Equal("ConvId", session!.ConversationId);
    }

    #endregion

    #region ChatHistoryProvider Override Tests

    /// <summary>
    /// Tests that RunAsync uses an override ChatHistoryProvider provided via AdditionalProperties instead of the provider from a factory
    /// if one is supplied.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesOverrideChatHistoryProvider_WhenProvidedViaAdditionalPropertiesAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        // Arrange a chat history provider to override the factory provided one.
        Mock<ChatHistoryProvider> mockOverrideChatHistoryProvider = new(null, null);
        mockOverrideChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(new List<ChatMessage> { new(ChatRole.User, "Existing Chat History") }.Concat(ctx.RequestMessages).ToList()));
        mockOverrideChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        // Arrange a chat history provider to provide to the agent at construction time.
        // This one shouldn't be used since it is being overridden.
        Mock<ChatHistoryProvider> mockAgentOptionsChatHistoryProvider = new(null, null);
        mockAgentOptionsChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ThrowsAsync(FailException.ForFailure("Base ChatHistoryProvider shouldn't be used."));
        mockAgentOptionsChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Throws(FailException.ForFailure("Base ChatHistoryProvider shouldn't be used."));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = mockAgentOptionsChatHistoryProvider.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        AdditionalPropertiesDictionary additionalProperties = new();
        additionalProperties.Add(mockOverrideChatHistoryProvider.Object);
        await agent.RunAsync([new(ChatRole.User, "test")], session, options: new AgentRunOptions { AdditionalProperties = additionalProperties });

        // Assert
        Assert.Same(mockAgentOptionsChatHistoryProvider.Object, agent.ChatHistoryProvider);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockOverrideChatHistoryProvider
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokingContext>(x => x.RequestMessages.Count() == 1),
                ItExpr.IsAny<CancellationToken>());
        mockOverrideChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 2 && x.ResponseMessages!.Count() == 1),
                ItExpr.IsAny<CancellationToken>());

        mockAgentOptionsChatHistoryProvider
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Never(),
                ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(),
                ItExpr.IsAny<CancellationToken>());
        mockAgentOptionsChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Never(),
                ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(),
                ItExpr.IsAny<CancellationToken>());
    }

    #endregion
}
