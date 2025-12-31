// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Contains unit tests for the ChatClientAgent.GetNewThread methods.
/// </summary>
public class ChatClientAgent_GetNewThreadTests
{
    [Fact]
    public void GetNewThread_UsesAIContextProviderFactory_IfProvided()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockContextProvider = new Mock<AIContextProvider>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" },
            AIContextProviderFactory = _ =>
            {
                factoryCalled = true;
                return mockContextProvider.Object;
            }
        });

        // Act
        var thread = agent.GetNewThread();

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    [Fact]
    public void GetNewThread_UsesChatMessageStoreFactory_IfProvided()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" },
            ChatMessageStoreFactory = _ =>
            {
                factoryCalled = true;
                return mockMessageStore.Object;
            }
        });

        // Act
        var thread = agent.GetNewThread();

        // Assert
        Assert.True(factoryCalled, "ChatMessageStoreFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }

    [Fact]
    public void GetNewThread_UsesChatMessageStore_FromTypedOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var thread = agent.GetNewThread(mockMessageStore.Object);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }

    [Fact]
    public void GetNewThread_UsesConversationId_FromTypedOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        const string TestConversationId = "test_conversation_id";
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var thread = agent.GetNewThread(TestConversationId);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Equal(TestConversationId, typedThread.ConversationId);
    }

    [Fact]
    public void GetNewThread_UsesConversationId_FromFeatureOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var testConversationId = new ConversationIdAgentFeature("test_conversation_id");
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(testConversationId);
        var thread = agent.GetNewThread(agentFeatures);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Equal(testConversationId.ConversationId, typedThread.ConversationId);
    }

    [Fact]
    public void GetNewThread_UsesChatMessageStore_FromFeatureOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(mockMessageStore.Object);
        var thread = agent.GetNewThread(agentFeatures);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }

    [Fact]
    public void GetNewThread_UsesAIContextProvider_FromFeatureOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockContextProvider = new Mock<AIContextProvider>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(mockContextProvider.Object);
        var thread = agent.GetNewThread(agentFeatures);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    [Fact]
    public void GetNewThread_Throws_IfBothConversationIdAndMessageStoreAreSet()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var testConversationId = new ConversationIdAgentFeature("test_conversation_id");
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act & Assert
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(mockMessageStore.Object);
        agentFeatures.Set(testConversationId);

        var exception = Assert.Throws<InvalidOperationException>(() => agent.GetNewThread(agentFeatures));
        Assert.Equal("Only the ConversationId or MessageStore may be set, but not both and switching from one to another is not supported.", exception.Message);
    }
}
