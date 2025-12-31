// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Contains unit tests for the ChatClientAgent.DeserializeThread methods.
/// </summary>
public class ChatClientAgent_DeserializeThreadTests
{
    [Fact]
    public void DeserializeThread_UsesAIContextProviderFactory_IfProvided()
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

        var json = JsonSerializer.Deserialize("""
            {
                "aiContextProviderState": ["CP1"]
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = agent.DeserializeThread(json);

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    [Fact]
    public void DeserializeThread_UsesChatMessageStoreFactory_IfProvided()
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

        var json = JsonSerializer.Deserialize("""
            {
                "storeState": { }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = agent.DeserializeThread(json);

        // Assert
        Assert.True(factoryCalled, "ChatMessageStoreFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }

    [Fact]
    public void DeserializeThread_UsesChatMessageStore_FromFeatureOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Instructions = "Test instructions" },
            ChatMessageStoreFactory = _ =>
            {
                Assert.Fail("ChatMessageStoreFactory should not have been called.");
                return null!;
            }
        });

        var json = JsonSerializer.Deserialize("""
            {
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(mockMessageStore.Object);
        var thread = agent.DeserializeThread(json, null, agentFeatures);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }

    [Fact]
    public void DeserializeThread_UsesAIContextProvider_FromFeatureOverload()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockContextProvider = new Mock<AIContextProvider>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Instructions = "Test instructions" },
            AIContextProviderFactory = _ =>
            {
                Assert.Fail("AIContextProviderFactory should not have been called.");
                return null!;
            }
        });

        var json = JsonSerializer.Deserialize("""
            {
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var agentFeatures = new AgentFeatureCollection();
        agentFeatures.Set(mockContextProvider.Object);
        var thread = agent.DeserializeThread(json, null, agentFeatures);

        // Assert
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }
}
