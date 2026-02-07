// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.Declarative.AzureAI.UnitTests;

/// <summary>
/// Unit tests for <see cref="OpenAIPromptAgentFactory"/>.
/// </summary>
public sealed class OpenAIPromptAgentFactoryTests
{
    [Fact]
    public void Constructor_WithChatClient_ThrowsForNull()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new OpenAIPromptAgentFactory(chatClient: null!));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsForNullPromptAgentAsync()
    {
        // Arrange
        OpenAIPromptAgentFactory factory = new();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => factory.TryCreateAsync(null!));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsWhenModelIsNullAsync()
    {
        // Arrange
        OpenAIPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = new("TestAgent");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => factory.TryCreateAsync(null!));
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsUnknownAsync()
    {
        // Arrange
        OpenAIPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Unknown");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsResponsesAsync()
    {
        // Arrange
        OpenAIPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Responses");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsAssistantsAsync()
    {
        // Arrange
        OpenAIPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Assistants");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsChatClientAgent_WhenChatClientProvidedAsync()
    {
        // Arrange
        ChatClient chatClient = new("gpt-4o", "test-api-key");
        OpenAIPromptAgentFactory factory = new(chatClient);
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Chat");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ChatClientAgent>(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsChatClientAgent_WithCorrectOptionsAsync()
    {
        // Arrange
        ChatClient chatClient = new("gpt-4o", "test-api-key");
        OpenAIPromptAgentFactory factory = new(chatClient);
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Chat");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(result);
        ChatClientAgent agent = Assert.IsType<ChatClientAgent>(result);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test Description", agent.Description);
    }

    private static GptComponentMetadata CreateTestPromptAgent(string apiType)
    {
        string agentYaml =
            $"""
            kind: Prompt
            name: Test Agent
            description: Test Description
            instructions: You are a helpful assistant.
            model:
              id: gpt-4o
              apiType: {apiType}
            """;

        return AgentBotElementYaml.FromYaml(agentYaml);
    }
}
