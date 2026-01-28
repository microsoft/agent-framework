// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotClientExtensions"/> class.
/// </summary>
public sealed class CopilotClientExtensionsTests
{
    [Fact]
    public void AsAIAgent_WithAllParameters_ReturnsGitHubCopilotAgentWithSpecifiedProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        const string TestId = "test-agent-id";
        const string TestName = "Test Agent";
        const string TestDescription = "This is a test agent description";

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: false, id: TestId, name: TestName, description: TestDescription, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithMinimalParameters_ReturnsGitHubCopilotAgent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: false, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        CopilotClient? copilotClient = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => copilotClient!.AsAIAgent(sessionConfig: null));
    }

    [Fact]
    public void AsAIAgent_WithOwnsClient_ReturnsAgentThatOwnsClient()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: true, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithTools_ReturnsAgentWithTools()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = copilotClient.AsAIAgent(tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }
}
