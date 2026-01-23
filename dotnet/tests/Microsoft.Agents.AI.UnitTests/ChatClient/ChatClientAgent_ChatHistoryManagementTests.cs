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
/// e.g. that it correctly reads and updates chat history in any available <see cref="ChatMessageStore"/> or that
/// it uses conversation id correctly for service managed chat history.
/// </summary>
public class ChatClientAgent_ChatHistoryManagementTests
{
    #region ConversationId Tests

    /// <summary>
    /// Verify that RunAsync does not throw when providing a ConversationId via both AgentThread and
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

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act & Assert
        var response = await agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions));
        Assert.NotNull(response);
    }

    /// <summary>
    /// Verify that RunAsync throws when providing a ConversationId via both AgentThread and
    /// via ChatOptions and the two are different.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenSpecifyingTwoDifferentConversationIdsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { ConversationId = "ConvId" };
        Mock<IChatClient> mockService = new();

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentThread thread = new() { ConversationId = "ThreadId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions)));
    }

    /// <summary>
    /// Verify that RunAsync clones the ChatOptions when providing a thread with a ConversationId and a ChatOptions.
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

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions));

        // Assert
        Assert.Null(chatOptions.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync throws if a thread is provided that uses a conversation id already, but the service does not return one on invoke.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_ForMissingConversationIdWithConversationIdThreadAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread));
    }

    /// <summary>
    /// Verify that RunAsync sets the ConversationId on the thread when the service returns one.
    /// </summary>
    [Fact]
    public async Task RunAsync_SetsConversationIdOnThread_WhenReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });
        ChatClientAgentThread thread = new();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        Assert.Equal("ConvId", thread.ConversationId);
    }

    #endregion

    #region ChatMessageStore Tests

    /// <summary>
    /// Verify that RunAsync uses the default InMemoryChatMessageStore when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesDefaultInMemoryChatMessageStore_WhenNoConversationIdReturnedByChatClientAsync()
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
        ChatClientAgentThread? thread = await agent.GetNewThreadAsync() as ChatClientAgentThread;
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        var messageStore = Assert.IsType<InMemoryChatMessageStore>(thread!.MessageStore);
        Assert.Equal(2, messageStore.Count);
        Assert.Equal("test", messageStore[0].Text);
        Assert.Equal("response", messageStore[1].Text);
    }

    /// <summary>
    /// Verify that RunAsync uses the ChatMessageStore factory when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesChatMessageStoreFactory_WhenProvidedAndNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatMessageStore> mockChatMessageStore = new();
        mockChatMessageStore.Setup(s => s.InvokingAsync(
            It.IsAny<ChatMessageStore.InvokingContext>(),
            It.IsAny<CancellationToken>())).ReturnsAsync([new ChatMessage(ChatRole.User, "Existing Chat History")]);
        mockChatMessageStore.Setup(s => s.InvokedAsync(
            It.IsAny<ChatMessageStore.InvokedContext>(),
            It.IsAny<CancellationToken>())).Returns(new ValueTask());

        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, CancellationToken, ValueTask<ChatMessageStore>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockChatMessageStore.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = await agent.GetNewThreadAsync() as ChatClientAgentThread;
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        Assert.IsType<ChatMessageStore>(thread!.MessageStore, exactMatch: false);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockChatMessageStore.Verify(s => s.InvokingAsync(
            It.Is<ChatMessageStore.InvokingContext>(x => x.RequestMessages.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockChatMessageStore.Verify(s => s.InvokedAsync(
            It.Is<ChatMessageStore.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ChatMessageStoreMessages != null && x.ChatMessageStoreMessages.Count() == 1 && x.ResponseMessages!.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync notifies the ChatMessageStore on failure.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesChatMessageStore_OnFailureAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Throws(new InvalidOperationException("Test Error"));

        Mock<ChatMessageStore> mockChatMessageStore = new();

        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, CancellationToken, ValueTask<ChatMessageStore>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockChatMessageStore.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = await agent.GetNewThreadAsync() as ChatClientAgentThread;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread));

        // Assert
        Assert.IsType<ChatMessageStore>(thread!.MessageStore, exactMatch: false);
        mockChatMessageStore.Verify(s => s.InvokedAsync(
            It.Is<ChatMessageStore.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ResponseMessages == null && x.InvokeException!.Message == "Test Error"),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync throws when a ChatMessageStore Factory is provided and the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenChatMessageStoreFactoryProvidedAndConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, CancellationToken, ValueTask<ChatMessageStore>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(new InMemoryChatMessageStore());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act & Assert
        ChatClientAgentThread? thread = await agent.GetNewThreadAsync() as ChatClientAgentThread;
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread));
        Assert.Equal("Only the ConversationId or MessageStore may be set, but not both and switching from one to another is not supported.", exception.Message);
    }

    #endregion

    #region ChatMessageStore Override Tests

    /// <summary>
    /// Tests that RunAsync uses an override ChatMessageStore provided via AdditionalProperties instead of the store from a factory
    /// if one is supplied.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesOverrideChatMessageStore_WhenProvidedViaAdditionalPropertiesAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        // Arrange a chat message store to override the factory provided one.
        Mock<ChatMessageStore> mockOverrideChatMessageStore = new();
        mockOverrideChatMessageStore.Setup(s => s.InvokingAsync(
            It.IsAny<ChatMessageStore.InvokingContext>(),
            It.IsAny<CancellationToken>())).ReturnsAsync([new ChatMessage(ChatRole.User, "Existing Chat History")]);
        mockOverrideChatMessageStore.Setup(s => s.InvokedAsync(
            It.IsAny<ChatMessageStore.InvokedContext>(),
            It.IsAny<CancellationToken>())).Returns(new ValueTask());

        // Arrange a chat message store to provide to the agent via a factory at construction time.
        // This one shouldn't be used since it is being overridden.
        Mock<ChatMessageStore> mockFactoryChatMessageStore = new();
        mockFactoryChatMessageStore.Setup(s => s.InvokingAsync(
            It.IsAny<ChatMessageStore.InvokingContext>(),
            It.IsAny<CancellationToken>())).ThrowsAsync(FailException.ForFailure("Base ChatMessageStore shouldn't be used."));
        mockFactoryChatMessageStore.Setup(s => s.InvokedAsync(
            It.IsAny<ChatMessageStore.InvokedContext>(),
            It.IsAny<CancellationToken>())).Throws(FailException.ForFailure("Base ChatMessageStore shouldn't be used."));

        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, CancellationToken, ValueTask<ChatMessageStore>>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>(), It.IsAny<CancellationToken>())).ReturnsAsync(mockFactoryChatMessageStore.Object);

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = await agent.GetNewThreadAsync() as ChatClientAgentThread;
        var additionalProperties = new AdditionalPropertiesDictionary();
        additionalProperties.Add(mockOverrideChatMessageStore.Object);
        await agent.RunAsync([new(ChatRole.User, "test")], thread, options: new AgentRunOptions { AdditionalProperties = additionalProperties });

        // Assert
        Assert.Same(mockFactoryChatMessageStore.Object, thread!.MessageStore);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == 2 && msgs.Any(m => m.Text == "Existing Chat History") && msgs.Any(m => m.Text == "test")),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockOverrideChatMessageStore.Verify(s => s.InvokingAsync(
            It.Is<ChatMessageStore.InvokingContext>(x => x.RequestMessages.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);
        mockOverrideChatMessageStore.Verify(s => s.InvokedAsync(
            It.Is<ChatMessageStore.InvokedContext>(x => x.RequestMessages.Count() == 1 && x.ChatMessageStoreMessages != null && x.ChatMessageStoreMessages.Count() == 1 && x.ResponseMessages!.Count() == 1),
            It.IsAny<CancellationToken>()),
            Times.Once);

        mockFactoryChatMessageStore.Verify(s => s.InvokingAsync(
            It.IsAny<ChatMessageStore.InvokingContext>(),
            It.IsAny<CancellationToken>()),
            Times.Never);
        mockFactoryChatMessageStore.Verify(s => s.InvokedAsync(
            It.IsAny<ChatMessageStore.InvokedContext>(),
            It.IsAny<CancellationToken>()),
            Times.Never);
    }

    #endregion
}
