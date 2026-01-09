// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Contains unit tests for the ChatClientAgent.DeserializeThread methods.
/// </summary>
public class ChatClientAgent_DeserializeThreadTests
{
    [Fact]
    public async Task DeserializeThread_UsesAIContextProviderFactory_IfProvidedAsync()
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

        var json = JsonSerializer.Deserialize("""
            {
                "aiContextProviderState": ["CP1"]
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = await agent.DeserializeThreadAsync(json);

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    [Fact]
    public async Task DeserializeThread_UsesChatMessageStoreFactory_IfProvidedAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockMessageStore = new Mock<ChatMessageStore>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" },
            ChatMessageStoreFactory = (_, _) =>
            {
                factoryCalled = true;
                return new ValueTask<ChatMessageStore>(mockMessageStore.Object);
            }
        });

        var json = JsonSerializer.Deserialize("""
            {
                "storeState": { }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = await agent.DeserializeThreadAsync(json);

        // Assert
        Assert.True(factoryCalled, "ChatMessageStoreFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockMessageStore.Object, typedThread.MessageStore);
    }
}
