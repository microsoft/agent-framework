// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.ObjectModel;
using Moq;

namespace Microsoft.Agents.AI.Declarative.AzureAI.UnitTests;

/// <summary>
/// Unit tests for <see cref="AzureAIPromptAgentFactory"/>.
/// </summary>
public sealed class AzureAIPromptAgentFactoryTests
{
    [Fact]
    public void Constructor_WithProjectClient_ThrowsForNull()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AzureAIPromptAgentFactory(projectClient: null!));
    }

    [Fact]
    public void Constructor_WithTokenCredential_ThrowsForNull()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AzureAIPromptAgentFactory(tokenCredential: null!));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsForNullPromptAgentAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => factory.TryCreateAsync(null!));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsForNullOrEmptyNameAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);
        GptComponentMetadata promptAgent = new(name: null!);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => factory.TryCreateAsync(promptAgent));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsForEmptyNameAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);
        GptComponentMetadata promptAgent = new(name: string.Empty);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => factory.TryCreateAsync(promptAgent));
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsWhenModelIdIsNullAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);
        GptComponentMetadata promptAgent = new("TestAgent");

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => factory.TryCreateAsync(promptAgent));
        Assert.Contains("AIProjectClient", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsWhenNoProjectClientAndNoConnectionAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);
        GptComponentMetadata promptAgent = CreateTestPromptAgentWithoutConnection();

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => factory.TryCreateAsync(promptAgent));
        Assert.Contains("AIProjectClient must be registered", exception.Message);
    }

    [Fact]
    public async Task TryCreateAsync_ThrowsWhenEndpointIsEmptyAsync()
    {
        // Arrange
        Mock<TokenCredential> mockCredential = new();
        AzureAIPromptAgentFactory factory = new(mockCredential.Object);
        GptComponentMetadata promptAgent = CreateTestPromptAgentWithEmptyEndpoint();

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => factory.TryCreateAsync(promptAgent));
        Assert.Contains("endpoint must be specified", exception.Message);
    }

    private static GptComponentMetadata CreateTestPromptAgentWithoutConnection()
    {
        const string agentYaml =
            """
            kind: Prompt
            name: Test Agent
            description: Test Description
            instructions: You are a helpful assistant.
            model:
              id: gpt-4o
            """;

        return AgentBotElementYaml.FromYaml(agentYaml);
    }

    private static GptComponentMetadata CreateTestPromptAgentWithEmptyEndpoint()
    {
        const string agentYaml =
            """
            kind: Prompt
            name: Test Agent
            description: Test Description
            instructions: You are a helpful assistant.
            model:
              id: gpt-4o
              connection:
                kind: Remote
                endpoint: ""
            """;

        return AgentBotElementYaml.FromYaml(agentYaml);
    }
}
