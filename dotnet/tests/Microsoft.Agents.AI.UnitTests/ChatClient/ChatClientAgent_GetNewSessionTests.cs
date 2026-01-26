// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the ChatClientAgent.GetNewSessionAsync methods.
/// </summary>
public class ChatClientAgent_GetNewSessionTests
{
    [Fact]
    public async Task GetNewSession_UsesAIContextProviderFactory_IfProvidedAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockContextProvider = new Mock<AIContextProvider>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" },
            AIContextProviderFactory = (_, _) =>
            {
                factoryCalled = true;
                return new ValueTask<AIContextProvider>(mockContextProvider.Object);
            }
        });

        // Act
        var session = await agent.GetNewSessionAsync();

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentSession>(session);
        var typedSession = (ChatClientAgentSession)session;
        Assert.Same(mockContextProvider.Object, typedSession.AIContextProvider);
    }

    [Fact]
    public async Task GetNewSession_UsesChatHistoryProviderFactory_IfProvidedAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" },
            ChatHistoryProviderFactory = (_, _) =>
            {
                factoryCalled = true;
                return new ValueTask<ChatHistoryProvider>(mockChatHistoryProvider.Object);
            }
        });

        // Act
        var session = await agent.GetNewSessionAsync();

        // Assert
        Assert.True(factoryCalled, "ChatHistoryProviderFactory was not called.");
        Assert.IsType<ChatClientAgentSession>(session);
        var typedSession = (ChatClientAgentSession)session;
        Assert.Same(mockChatHistoryProvider.Object, typedSession.ChatHistoryProvider);
    }

    [Fact]
    public async Task GetNewSession_UsesChatHistoryProvider_FromTypedOverloadAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var session = await agent.GetNewSessionAsync(mockChatHistoryProvider.Object);

        // Assert
        Assert.IsType<ChatClientAgentSession>(session);
        var typedSession = (ChatClientAgentSession)session;
        Assert.Same(mockChatHistoryProvider.Object, typedSession.ChatHistoryProvider);
    }

    [Fact]
    public async Task GetNewSession_UsesConversationId_FromTypedOverloadAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        const string TestConversationId = "test_conversation_id";
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var session = await agent.GetNewSessionAsync(TestConversationId);

        // Assert
        Assert.IsType<ChatClientAgentSession>(session);
        var typedSession = (ChatClientAgentSession)session;
        Assert.Equal(TestConversationId, typedSession.ConversationId);
    }
}
