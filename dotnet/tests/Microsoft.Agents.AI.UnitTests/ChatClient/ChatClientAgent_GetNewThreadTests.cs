// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the ChatClientAgent.GetNewThreadAsync methods.
/// </summary>
public class ChatClientAgent_GetNewThreadTests
{
    [Fact]
    public async Task GetNewThread_UsesAIContextProviderFactory_IfProvidedAsync()
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
        var thread = await agent.GetNewThreadAsync();

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    [Fact]
    public async Task GetNewThread_UsesChatHistoryProviderFactory_IfProvidedAsync()
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
        var thread = await agent.GetNewThreadAsync();

        // Assert
        Assert.True(factoryCalled, "ChatHistoryProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockChatHistoryProvider.Object, typedThread.ChatHistoryProvider);
    }

    [Fact]
    public async Task GetNewThread_UsesChatHistoryProvider_FromTypedOverloadAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var thread = await agent.GetNewThreadAsync(mockChatHistoryProvider.Object);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockChatHistoryProvider.Object, typedThread.ChatHistoryProvider);
    }

    [Fact]
    public async Task GetNewThread_UsesConversationId_FromTypedOverloadAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        const string TestConversationId = "test_conversation_id";
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var thread = await agent.GetNewThreadAsync(TestConversationId);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Equal(TestConversationId, typedThread.ConversationId);
    }
}
