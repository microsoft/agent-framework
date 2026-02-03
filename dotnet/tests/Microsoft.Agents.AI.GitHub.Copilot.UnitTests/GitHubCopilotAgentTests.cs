// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="GitHubCopilotAgent"/> class.
/// </summary>
public sealed class GitHubCopilotAgentTests
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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, name: TestName, description: TestDescription, tools: null);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void Constructor_WithNullCopilotClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new GitHubCopilotAgent(copilotClient: null!, sessionConfig: null));
    }

    [Fact]
    public void Constructor_WithDefaultParameters_UsesBaseProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        // Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);
        Assert.Equal("GitHub Copilot Agent", agent.Name);
        Assert.Equal("An AI agent powered by GitHub Copilot", agent.Description);
    }

    [Fact]
    public async Task CreateSessionAsync_ReturnsGitHubCopilotAgentSessionAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        // Act
        var session = await agent.CreateSessionAsync();

        // Assert
        Assert.NotNull(session);
        Assert.IsType<GitHubCopilotAgentSession>(session);
    }

    [Fact]
    public async Task CreateSessionAsync_WithSessionId_ReturnsSessionWithSessionIdAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        const string TestSessionId = "test-session-id";

        // Act
        var session = await agent.CreateSessionAsync(TestSessionId);

        // Assert
        Assert.NotNull(session);
        var typedSession = Assert.IsType<GitHubCopilotAgentSession>(session);
        Assert.Equal(TestSessionId, typedSession.SessionId);
    }

    [Fact]
    public void Constructor_WithTools_InitializesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Id);
    }
}
