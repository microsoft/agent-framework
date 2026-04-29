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
    private static readonly PermissionRequestHandler s_testPermissionHandler = (_, _) => Task.FromResult(new PermissionRequestResult { Kind = PermissionRequestResultKind.Approved });

    [Fact]
    public void Constructor_WithCopilotClient_InitializesPropertiesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        const string TestId = "test-id";
        const string TestName = "test-name";
        const string TestDescription = "test-description";

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, name: TestName, description: TestDescription, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);

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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: null, name: null, description: null, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);

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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: null, name: null, description: null, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);

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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: null, name: null, description: null, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);
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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: null, name: null, description: null, tools: tools, instructions: null, onPermissionRequest: s_testPermissionHandler);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Id);
    }

    [Fact]
    public void CopySessionConfig_CopiesAllProperties()
    {
        // Arrange
        List<AIFunction> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
        PermissionRequestHandler permissionHandler = (_, _) => Task.FromResult(new PermissionRequestResult());
        UserInputHandler userInputHandler = (_, _) => Task.FromResult(new UserInputResponse { Answer = "input" });
        var mcpServers = new Dictionary<string, McpServerConfig> { ["server1"] = new McpStdioServerConfig { Command = "echo" } };

        var source = new SessionConfig
        {
            Model = "gpt-4o",
            ReasoningEffort = "high",
            Tools = tools,
            SystemMessage = systemMessage,
            AvailableTools = ["tool1", "tool2"],
            ExcludedTools = ["tool3"],
            WorkingDirectory = "/workspace",
            ConfigDir = "/config",
            Hooks = hooks,
            InfiniteSessions = infiniteSessions,
            OnPermissionRequest = permissionHandler,
            OnUserInputRequest = userInputHandler,
            McpServers = mcpServers,
            DisabledSkills = ["skill1"],
            GitHubToken = "test-token",
        };

        // Act
        SessionConfig result = GitHubCopilotAgent.CopySessionConfig(source);

        // Assert
        Assert.Equal("gpt-4o", result.Model);
        Assert.Equal("high", result.ReasoningEffort);
        Assert.Same(tools, result.Tools);
        Assert.Same(systemMessage, result.SystemMessage);
        Assert.Equal(new List<string> { "tool1", "tool2" }, result.AvailableTools);
        Assert.Equal(new List<string> { "tool3" }, result.ExcludedTools);
        Assert.Equal("/workspace", result.WorkingDirectory);
        Assert.Equal("/config", result.ConfigDir);
        Assert.Same(hooks, result.Hooks);
        Assert.Same(infiniteSessions, result.InfiniteSessions);
        Assert.Same(permissionHandler, result.OnPermissionRequest);
        Assert.Same(userInputHandler, result.OnUserInputRequest);
        Assert.Same(mcpServers, result.McpServers);
        Assert.Equal(new List<string> { "skill1" }, result.DisabledSkills);
        Assert.Equal("test-token", result.GitHubToken);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_CopiesAllProperties()
    {
        // Arrange
        List<AIFunction> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
        PermissionRequestHandler permissionHandler = (_, _) => Task.FromResult(new PermissionRequestResult());
        UserInputHandler userInputHandler = (_, _) => Task.FromResult(new UserInputResponse { Answer = "input" });
        var mcpServers = new Dictionary<string, McpServerConfig> { ["server1"] = new McpStdioServerConfig { Command = "echo" } };

        var source = new SessionConfig
        {
            Model = "gpt-4o",
            ReasoningEffort = "high",
            Tools = tools,
            SystemMessage = systemMessage,
            AvailableTools = ["tool1", "tool2"],
            ExcludedTools = ["tool3"],
            WorkingDirectory = "/workspace",
            ConfigDir = "/config",
            Hooks = hooks,
            InfiniteSessions = infiniteSessions,
            OnPermissionRequest = permissionHandler,
            OnUserInputRequest = userInputHandler,
            McpServers = mcpServers,
            DisabledSkills = ["skill1"],
            GitHubToken = "test-token",
        };

        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(source);

        // Assert
        Assert.Equal("gpt-4o", result.Model);
        Assert.Equal("high", result.ReasoningEffort);
        Assert.Same(tools, result.Tools);
        Assert.Same(systemMessage, result.SystemMessage);
        Assert.Equal(new List<string> { "tool1", "tool2" }, result.AvailableTools);
        Assert.Equal(new List<string> { "tool3" }, result.ExcludedTools);
        Assert.Equal("/workspace", result.WorkingDirectory);
        Assert.Equal("/config", result.ConfigDir);
        Assert.Same(hooks, result.Hooks);
        Assert.Same(infiniteSessions, result.InfiniteSessions);
        Assert.Same(permissionHandler, result.OnPermissionRequest);
        Assert.Same(userInputHandler, result.OnUserInputRequest);
        Assert.Same(mcpServers, result.McpServers);
        Assert.Equal(new List<string> { "skill1" }, result.DisabledSkills);
        Assert.Equal("test-token", result.GitHubToken);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_WithNullSource_ReturnsDefaults()
    {
        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(null);

        // Assert
        Assert.Null(result.Model);
        Assert.Null(result.ReasoningEffort);
        Assert.Null(result.Tools);
        Assert.Null(result.SystemMessage);
        Assert.Null(result.OnPermissionRequest);
        Assert.Null(result.OnUserInputRequest);
        Assert.Null(result.Hooks);
        Assert.Null(result.WorkingDirectory);
        Assert.Null(result.ConfigDir);
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
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        const string TestId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, name: null, description: null, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage);

        // result.Text need to be empty because the content was already delivered via delta events, and we want to avoid emitting duplicate content in the response update.
        // The content should be delivered through TextContent in the Contents collection instead.
        Assert.Empty(result.Text);
        Assert.DoesNotContain(result.Contents, c => c is TextContent);
    }

    [Fact]
    public void Constructor_WithSessionConfig_InitializesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var sessionConfig = new SessionConfig
        {
            OnPermissionRequest = s_testPermissionHandler,
            Model = "gpt-4o",
        };

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, sessionConfig: sessionConfig, id: "cfg-id", name: "Cfg Agent");

        // Assert
        Assert.Equal("cfg-id", agent.Id);
        Assert.Equal("Cfg Agent", agent.Name);
    }

    [Fact]
    public void Constructor_WithToolsAndPermissionHandler_InitializesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = new GitHubCopilotAgent(
            copilotClient,
            ownsClient: false,
            id: "tool-agent",
            name: "Tool Agent",
            description: "Agent with tools",
            tools: tools,
            instructions: "Be helpful",
            onPermissionRequest: s_testPermissionHandler);

        // Assert
        Assert.Equal("tool-agent", agent.Id);
        Assert.Equal("Tool Agent", agent.Name);
        Assert.Equal("Agent with tools", agent.Description);
    }

    [Fact]
    public void OldConstructor_WithoutPermissionHandler_IsMarkedObsoleteWithError()
    {
        // The old constructor (tools/instructions without onPermissionRequest) should be
        // marked with [Obsolete(error: true)], causing a compile error if used directly.
        // Verify via reflection that the attribute is present and is an error.
        var oldCtor = typeof(GitHubCopilotAgent).GetConstructor(new[]
        {
            typeof(CopilotClient),
            typeof(bool),
            typeof(string),
            typeof(string),
            typeof(string),
            typeof(IList<AITool>),
            typeof(string),
        });

        Assert.NotNull(oldCtor);
        var obsoleteAttr = oldCtor!.GetCustomAttributes(typeof(ObsoleteAttribute), false);
        Assert.Single(obsoleteAttr);
        var attr = (ObsoleteAttribute)obsoleteAttr[0];
        Assert.True(attr.IsError);
        Assert.Contains("OnPermissionRequest", attr.Message);
    }
}
