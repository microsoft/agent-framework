// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GithubCopilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="GithubCopilotAgent"/> class.
/// </summary>
public sealed class GithubCopilotAgentTests
{
    [Fact]
    public void Constructor_WithCopilotClient_InitializesPropertiesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        const string TestId = "test-id";
        const string TestName = "test-name";
        const string TestDescription = "test-description";

        // Act
        var agent = new GithubCopilotAgent(copilotClient, id: TestId, name: TestName, description: TestDescription);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void Constructor_WithNullCopilotClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new GithubCopilotAgent(null!));
    }

    [Fact]
    public void Constructor_WithDefaultParameters_UsesBaseProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = new GithubCopilotAgent(copilotClient);

        // Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
    }

    [Fact]
    public async Task GetNewThreadAsync_ReturnsGithubCopilotAgentThreadAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GithubCopilotAgent(copilotClient);

        // Act
        var thread = await agent.GetNewThreadAsync();

        // Assert
        Assert.NotNull(thread);
        Assert.IsType<GithubCopilotAgentThread>(thread);
    }

    [Fact]
    public async Task GetNewThreadAsync_WithSessionId_ReturnsThreadWithSessionIdAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GithubCopilotAgent(copilotClient);
        const string TestSessionId = "test-session-id";

        // Act
        var thread = await agent.GetNewThreadAsync(TestSessionId);

        // Assert
        Assert.NotNull(thread);
        var typedThread = Assert.IsType<GithubCopilotAgentThread>(thread);
        Assert.Equal(TestSessionId, typedThread.SessionId);
    }

    [Fact]
    public void Constructor_WithTools_InitializesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = new GithubCopilotAgent(copilotClient, tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Id);
    }
}
