// Copyright (c) Microsoft. All rights reserved.

using System;
using GitHub.Copilot.SDK;

namespace Microsoft.Agents.AI.GithubCopilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotClientExtensions"/> class.
/// </summary>
public sealed class CopilotClientExtensionsTests
{
    [Fact]
    public void AsAIAgent_WithAllParameters_ReturnsGithubCopilotAgentWithSpecifiedProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        const string TestId = "test-agent-id";
        const string TestName = "Test Agent";
        const string TestDescription = "This is a test agent description";

        // Act
        var agent = copilotClient.AsAIAgent(id: TestId, name: TestName, description: TestDescription);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GithubCopilotAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithMinimalParameters_ReturnsGithubCopilotAgent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent();

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GithubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        CopilotClient? copilotClient = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => copilotClient!.AsAIAgent());
    }

    [Fact]
    public void AsAIAgent_WithOwnsClient_ReturnsAgentThatOwnsClient()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: true);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GithubCopilotAgent>(agent);
    }
}
