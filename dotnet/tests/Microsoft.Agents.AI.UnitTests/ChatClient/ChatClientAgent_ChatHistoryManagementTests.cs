// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
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
        InMemoryChatHistoryProvider chatHistoryProvider = Assert.IsType<InMemoryChatHistoryProvider>(session!.ChatHistoryProvider);
        Assert.Equal(2, chatHistoryProvider.Count);
        Assert.Equal("test", chatHistoryProvider[0].Text);
        Assert.Equal("response", chatHistoryProvider[1].Text);
    }

    /// <summary>
    /// Verify that RunAsync uses the ChatHistoryProvider factory when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesChatHistoryProviderFactory_WhenProvidedAndNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new();
        mockChatHistoryProvider.Setup(s => s.InvokingAsync(
            It.IsAny<ChatHistoryProvider.InvokingContext>(),
            It.IsAny<CancellationToken>())).ReturnsAsync([new ChatMessage(ChatRole.User, "Existing Chat History")]);
        mockChatHistoryProvider.Setup(s => s.InvokedAsync(
            It.IsAny<ChatHistoryProvider.InvokedContext>(),
            It.IsAny<CancellationToken>())).Returns(new ValueTask());

        Mock<Func<ChatClientAgentOptions.ChatHistoryProviderFactoryContext, CancellationToken, ValueTask<ChatHistoryProvider>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockChatHistoryProvider.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProviderFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.IsType<ChatHistoryProvider>(session!.ChatHistoryProvider, exactMatch: false);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockChatHistoryProvider.Verify(s => s.InvokingAsync(
            It.Is<ChatHistoryProvider.InvokingContext>(x => x.RequestMessages.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockChatHistoryProvider.Verify(s => s.InvokedAsync(
            It.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ChatHistoryProviderMessages != null && x.ChatHistoryProviderMessages.Count() == 1 && x.ResponseMessages!.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>()), Times.Once);
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

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new();

        Mock<Func<ChatClientAgentOptions.ChatHistoryProviderFactoryContext, CancellationToken, ValueTask<ChatHistoryProvider>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockChatHistoryProvider.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProviderFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert
        Assert.IsType<ChatHistoryProvider>(session!.ChatHistoryProvider, exactMatch: false);
        mockChatHistoryProvider.Verify(s => s.InvokedAsync(
            It.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ResponseMessages == null && x.InvokeException!.Message == "Test Error"),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync throws when a ChatHistoryProvider Factory is provided and the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenChatHistoryProviderFactoryProvidedAndConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        Mock<Func<ChatClientAgentOptions.ChatHistoryProviderFactoryContext, CancellationToken, ValueTask<ChatHistoryProvider>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(new InMemoryChatHistoryProvider());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProviderFactory = mockFactory.Object
        });

        // Act & Assert
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));
        Assert.Equal("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.", exception.Message);
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
        Mock<ChatHistoryProvider> mockOverrideChatHistoryProvider = new();
        mockOverrideChatHistoryProvider.Setup(s => s.InvokingAsync(
            It.IsAny<ChatHistoryProvider.InvokingContext>(),
            It.IsAny<CancellationToken>())).ReturnsAsync([new ChatMessage(ChatRole.User, "Existing Chat History")]);
        mockOverrideChatHistoryProvider.Setup(s => s.InvokedAsync(
            It.IsAny<ChatHistoryProvider.InvokedContext>(),
            It.IsAny<CancellationToken>())).Returns(new ValueTask());

        // Arrange a chat history provider to provide to the agent via a factory at construction time.
        // This one shouldn't be used since it is being overridden.
        Mock<ChatHistoryProvider> mockFactoryChatHistoryProvider = new();
        mockFactoryChatHistoryProvider.Setup(s => s.InvokingAsync(
            It.IsAny<ChatHistoryProvider.InvokingContext>(),
            It.IsAny<CancellationToken>())).ThrowsAsync(FailException.ForFailure("Base ChatHistoryProvider shouldn't be used."));
        mockFactoryChatHistoryProvider.Setup(s => s.InvokedAsync(
            It.IsAny<ChatHistoryProvider.InvokedContext>(),
            It.IsAny<CancellationToken>())).Throws(FailException.ForFailure("Base ChatHistoryProvider shouldn't be used."));

        Mock<Func<ChatClientAgentOptions.ChatHistoryProviderFactoryContext, CancellationToken, ValueTask<ChatHistoryProvider>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatHistoryProviderFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockFactoryChatHistoryProvider.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProviderFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        AdditionalPropertiesDictionary additionalProperties = new();
        additionalProperties.Add(mockOverrideChatHistoryProvider.Object);
        await agent.RunAsync([new(ChatRole.User, "test")], session, options: new AgentRunOptions { AdditionalProperties = additionalProperties });

        // Assert
        Assert.Same(mockFactoryChatHistoryProvider.Object, session!.ChatHistoryProvider);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockOverrideChatHistoryProvider.Verify(s => s.InvokingAsync(
            It.Is<ChatHistoryProvider.InvokingContext>(x => x.RequestMessages.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockOverrideChatHistoryProvider.Verify(s => s.InvokedAsync(
            It.Is<ChatHistoryProvider.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ChatHistoryProviderMessages != null && x.ChatHistoryProviderMessages.Count() == 1 && x.ResponseMessages!.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);

        mockFactoryChatHistoryProvider.Verify(s => s.InvokingAsync(
            It.IsAny<ChatHistoryProvider.InvokingContext>(),
            It.IsAny<CancellationToken>()),
            Times.Never);
        mockFactoryChatHistoryProvider.Verify(s => s.InvokedAsync(
            It.IsAny<ChatHistoryProvider.InvokedContext>(),
            It.IsAny<CancellationToken>()),
            Times.Never);
    }

    #endregion
}
