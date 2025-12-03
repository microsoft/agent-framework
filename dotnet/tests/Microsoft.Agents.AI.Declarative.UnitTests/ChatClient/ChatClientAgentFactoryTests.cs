// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Declarative.UnitTests.ChatClient;

/// <summary>
/// Unit tests for <see cref="ChatClientPromptAgentFactory"/>.
/// </summary>
public sealed class ChatClientAgentFactoryTests
{
    private readonly Mock<IChatClient> _mockChatClient;

    public ChatClientAgentFactoryTests()
    {
        this._mockChatClient = new();
    }

    [Fact]
    public async Task TryCreateAsync_WithChatClientInConstructor_CreatesAgentAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test Description", agent.Description);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ChatClientAgentAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent);
        Assert.Equal("You are a helpful assistant.", chatClientAgent.Instructions);
        Assert.NotNull(chatClientAgent.ChatClient);
        Assert.NotNull(chatClientAgent.ChatOptions);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ChatOptionsAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent?.ChatOptions);
        Assert.Equal("You are a helpful assistant.", chatClientAgent?.ChatOptions?.Instructions);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.Temperature);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.FrequencyPenalty);
        Assert.Equal(1024, chatClientAgent?.ChatOptions?.MaxOutputTokens);
        Assert.Equal(0.9F, chatClientAgent?.ChatOptions?.TopP);
        Assert.Equal(50, chatClientAgent?.ChatOptions?.TopK);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.PresencePenalty);
        Assert.Equal(42L, chatClientAgent?.ChatOptions?.Seed);
        Assert.NotNull(chatClientAgent?.ChatOptions?.ResponseFormat);
        Assert.Equal("gpt-4o", chatClientAgent?.ChatOptions?.ModelId);
        Assert.Equal(["###", "END", "STOP"], chatClientAgent?.ChatOptions?.StopSequences);
        Assert.True(chatClientAgent?.ChatOptions?.AllowMultipleToolCalls);
        Assert.Equal(ChatToolMode.Auto, chatClientAgent?.ChatOptions?.ToolMode);
        Assert.Equal("customValue", chatClientAgent?.ChatOptions?.AdditionalProperties?["customProperty"]);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ToolsAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent?.ChatOptions?.Tools);
        var tools = chatClientAgent?.ChatOptions?.Tools;
        Assert.Equal(5, tools?.Count);
    }
}
