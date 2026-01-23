// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

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
    public async Task DeserializeThread_UsesChatHistoryProviderFactory_IfProvidedAsync()
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

        var json = JsonSerializer.Deserialize("""
            {
                "chatHistoryProviderState": { }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = await agent.DeserializeThreadAsync(json);

        // Assert
        Assert.True(factoryCalled, "ChatHistoryProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockChatHistoryProvider.Object, typedThread.ChatHistoryProvider);
    }
}
