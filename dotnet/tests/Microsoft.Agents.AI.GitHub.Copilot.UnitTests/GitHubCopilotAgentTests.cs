// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using GitHub.Copilot;
using GitHub.Copilot.Rpc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="GitHubCopilotAgent"/> class.
/// </summary>
public sealed class GitHubCopilotAgentTests
{
    private static readonly Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> s_testPermissionHandler =
        (_, _) => Task.FromResult(PermissionDecision.ApproveOnce());

    [Fact]
    public void Constructor_WithCopilotClient_InitializesPropertiesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());
        const string TestId = "test-id";
        const string TestName = "test-name";
        const string TestDescription = "test-description";

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler, ownsClient: false, id: TestId, name: TestName, description: TestDescription);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void Constructor_WithNullCopilotClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new GitHubCopilotAgent(copilotClient: null!, sessionConfig: new() { OnPermissionRequest = s_testPermissionHandler }));
    }

    [Fact]
    public void Constructor_WithNullSessionConfig_ThrowsArgumentNullException()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new GitHubCopilotAgent(copilotClient, sessionConfig: null!));
    }

    [Fact]
    public void Constructor_WithNullPermissionHandler_ThrowsArgumentNullException()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new GitHubCopilotAgent(copilotClient, onPermissionRequest: null!));
    }

    [Fact]
    public void Constructor_WithDefaultParameters_UsesBaseProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler);

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
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler);

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
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler);
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
        CopilotClient copilotClient = new(new CopilotClientOptions());
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Id);
    }

    [Fact]
    public void Constructor_WithSessionConfig_InitializesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var sessionConfig = new SessionConfig
        {
            OnPermissionRequest = s_testPermissionHandler,
            Model = "gpt-5",
            GitHubToken = "per-session-token",
        };

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, sessionConfig, id: "cfg-id", name: "Cfg Agent");

        // Assert
        Assert.Equal("cfg-id", agent.Id);
        Assert.Equal("Cfg Agent", agent.Name);
    }

    [Fact]
    public void CopySessionConfig_ForwardsAllProperties_IncludingGitHubToken()
    {
        // Arrange
        var source = new SessionConfig
        {
            OnPermissionRequest = s_testPermissionHandler,
            Model = "gpt-5",
            ReasoningEffort = "high",
            GitHubToken = "per-session-token",
            WorkingDirectory = "/workspace",
            ConfigDirectory = "/config",
        };

        // Act
        SessionConfig result = GitHubCopilotAgent.CopySessionConfig(source);

        // Assert
        Assert.Equal("gpt-5", result.Model);
        Assert.Equal("high", result.ReasoningEffort);
        Assert.Equal("per-session-token", result.GitHubToken);
        Assert.Equal("/workspace", result.WorkingDirectory);
        Assert.Equal("/config", result.ConfigDirectory);
        Assert.Same(s_testPermissionHandler, result.OnPermissionRequest);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_ForwardsAllProperties_IncludingGitHubToken()
    {
        // Arrange
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
        var modelCapabilities = new ModelCapabilitiesOverride();
        var defaultAgent = new DefaultAgentConfig();
        var source = new SessionConfig
        {
            Model = "gpt-5",
            ReasoningEffort = "high",
            ModelCapabilities = modelCapabilities,
            SystemMessage = systemMessage,
            AvailableTools = ["tool1", "tool2"],
            ExcludedTools = ["tool3"],
            WorkingDirectory = "/workspace",
            ConfigDirectory = "/config",
            EnableConfigDiscovery = true,
            Hooks = hooks,
            InfiniteSessions = infiniteSessions,
            OnPermissionRequest = s_testPermissionHandler,
            DisabledSkills = ["skill1"],
            DefaultAgent = defaultAgent,
            Agent = "myagent",
            ClientName = "test-client",
            GitHubToken = "test-token",
        };

        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(source);

        // Assert
        Assert.Equal("gpt-5", result.Model);
        Assert.Equal("high", result.ReasoningEffort);
        Assert.Same(modelCapabilities, result.ModelCapabilities);
        Assert.Same(systemMessage, result.SystemMessage);
        Assert.Equal(new List<string> { "tool1", "tool2" }, result.AvailableTools);
        Assert.Equal(new List<string> { "tool3" }, result.ExcludedTools);
        Assert.Equal("/workspace", result.WorkingDirectory);
        Assert.Equal("/config", result.ConfigDirectory);
        Assert.Equal(true, result.EnableConfigDiscovery);
        Assert.Same(hooks, result.Hooks);
        Assert.Same(infiniteSessions, result.InfiniteSessions);
        Assert.Same(s_testPermissionHandler, result.OnPermissionRequest);
        Assert.Equal(new List<string> { "skill1" }, result.DisabledSkills);
        Assert.Same(defaultAgent, result.DefaultAgent);
        Assert.Equal("myagent", result.Agent);
        Assert.Equal("test-client", result.ClientName);
        Assert.Equal("test-token", result.GitHubToken);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_WithNullSource_ReturnsDefaultsWithStreamingTrue()
    {
        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(null);

        // Assert
        Assert.Null(result.Model);
        Assert.Null(result.ReasoningEffort);
        Assert.Null(result.SystemMessage);
        Assert.Null(result.OnPermissionRequest);
        Assert.Null(result.Hooks);
        Assert.Null(result.WorkingDirectory);
        Assert.Null(result.ConfigDirectory);
        Assert.Null(result.GitHubToken);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantMessageEvent_DoesNotEmitTextContent()
    {
        var assistantMessage = new AssistantMessageEvent
        {
            Data = new AssistantMessageData
            {
                MessageId = "msg-456",
                Content = "Some streamed content that was already delivered via delta events"
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        const string TestId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, s_testPermissionHandler, id: TestId);
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage);

        // result.Text need to be empty because the content was already delivered via delta events, and we want to avoid emitting duplicate content in the response update.
        // The content should be delivered through TextContent in the Contents collection instead.
        Assert.Empty(result.Text);
        Assert.DoesNotContain(result.Contents, c => c is TextContent);
    }
}
