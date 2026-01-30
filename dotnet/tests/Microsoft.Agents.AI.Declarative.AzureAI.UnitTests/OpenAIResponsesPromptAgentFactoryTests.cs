// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
using OpenAI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Declarative.AzureAI.UnitTests;

/// <summary>
/// Unit tests for <see cref="OpenAIResponsesPromptAgentFactory"/>.
/// </summary>
public sealed class OpenAIResponsesPromptAgentFactoryTests
{
    [Fact]
    public void Constructor_WithResponsesClient_ThrowsForNull()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new OpenAIResponsesPromptAgentFactory(responsesClient: null!));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsForNullPromptAgentAsync()
    {
        // Arrange
        OpenAIResponsesPromptAgentFactory factory = new();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => factory.TryCreateAsync(null!));
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenModelIsNullAsync()
    {
        // Arrange
        OpenAIResponsesPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = new("TestAgent");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsUnknownAsync()
    {
        // Arrange
        OpenAIResponsesPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Unknown");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsChatAsync()
    {
        // Arrange
        OpenAIResponsesPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Chat");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsNull_WhenApiTypeIsAssistantsAsync()
    {
        // Arrange
        OpenAIResponsesPromptAgentFactory factory = new();
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Assistants");

        // Act
        AIAgent? result = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task TryCreateAsync_ReturnsChatClientAgent_WhenResponsesClientProvidedAsync()
    {
        // Arrange
        ResponsesClient responsesClient = new OpenAIClient("test-api-key").GetResponsesClient("gpt-4o");
        OpenAIResponsesPromptAgentFactory factory = new(responsesClient);
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Responses");

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
        ResponsesClient responsesClient = new OpenAIClient("test-api-key").GetResponsesClient("gpt-4o");
        OpenAIResponsesPromptAgentFactory factory = new(responsesClient);
        GptComponentMetadata promptAgent = CreateTestPromptAgent(apiType: "Responses");

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
