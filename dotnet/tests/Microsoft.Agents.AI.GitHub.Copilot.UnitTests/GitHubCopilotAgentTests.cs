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
    [Fact]
    public void Constructor_WithCopilotClient_InitializesPropertiesCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());
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
        CopilotClient copilotClient = new(new CopilotClientOptions());

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
        CopilotClient copilotClient = new(new CopilotClientOptions());
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
        CopilotClient copilotClient = new(new CopilotClientOptions());
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
        CopilotClient copilotClient = new(new CopilotClientOptions());
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Id);
    }

    [Fact]
    public void CopySessionConfig_CopiesAllProperties()
    {
        // Arrange
        ICollection<AIFunctionDeclaration> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
#pragma warning disable GHCP001
        Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> permissionHandler = (_, _) => Task.FromResult(PermissionDecision.ApproveOnce());
#pragma warning restore GHCP001
        Func<UserInputRequest, UserInputInvocation, Task<UserInputResponse>> userInputHandler = (_, _) => Task.FromResult(new UserInputResponse { Answer = "input" });
        var mcpServers = new Dictionary<string, McpServerConfig> { ["server1"] = new McpStdioServerConfig() };

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
    }

    [Fact]
    public void CopyResumeSessionConfig_CopiesAllProperties()
    {
        // Arrange
        ICollection<AIFunctionDeclaration> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
#pragma warning disable GHCP001
        Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> permissionHandler = (_, _) => Task.FromResult(PermissionDecision.ApproveOnce());
#pragma warning restore GHCP001
        Func<UserInputRequest, UserInputInvocation, Task<UserInputResponse>> userInputHandler = (_, _) => Task.FromResult(new UserInputResponse { Answer = "input" });
        var mcpServers = new Dictionary<string, McpServerConfig> { ["server1"] = new McpStdioServerConfig() };

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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, tools: null);
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage);

        // result.Text need to be empty because the content was already delivered via delta events, and we want to avoid emitting duplicate content in the response update.
        // The content should be delivered through TextContent in the Contents collection instead.
        Assert.Empty(result.Text);
        Assert.DoesNotContain(result.Contents, c => c is TextContent);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantReasoningEvent_EmitsCopilotReasoningContent()
    {
        // Arrange
        var reasoningEvent = new AssistantReasoningEvent
        {
            Data = new AssistantReasoningData
            {
                Content = "The user wants a sorted list, so I should use a merge sort.",
                ReasoningId = "reasoning-1"
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-id", tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(reasoningEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var reasoning = Assert.IsType<CopilotReasoningContent>(content);
        Assert.Equal("The user wants a sorted list, so I should use a merge sort.", reasoning.Content);
        Assert.Equal("reasoning-1", reasoning.ReasoningId);
        Assert.Same(reasoningEvent, reasoning.RawRepresentation);
        Assert.Equal(ChatRole.Assistant, result.Role);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_EmitsCopilotToolExecutionContentStarted()
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-1",
                ToolName = "shell"
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-id", tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(toolStartEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var toolContent = Assert.IsType<CopilotToolExecutionContent>(content);
        Assert.Equal(CopilotToolExecutionPhase.Started, toolContent.Phase);
        Assert.Equal("call-1", toolContent.ToolCallId);
        Assert.Equal("shell", toolContent.ToolName);
        Assert.Same(toolStartEvent, toolContent.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionProgressEvent_EmitsCopilotToolExecutionContentProgress()
    {
        // Arrange
        var toolProgressEvent = new ToolExecutionProgressEvent
        {
            Data = new ToolExecutionProgressData
            {
                ToolCallId = "call-1",
                ProgressMessage = "Building project..."
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-id", tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(toolProgressEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var toolContent = Assert.IsType<CopilotToolExecutionContent>(content);
        Assert.Equal(CopilotToolExecutionPhase.Progress, toolContent.Phase);
        Assert.Equal("call-1", toolContent.ToolCallId);
        Assert.Equal("Building project...", toolContent.ProgressMessage);
        Assert.Same(toolProgressEvent, toolContent.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_Success_EmitsSuccessContent()
    {
        // Arrange
        var toolCompleteEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-1",
                Success = true
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-id", tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(toolCompleteEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var toolContent = Assert.IsType<CopilotToolExecutionContent>(content);
        Assert.Equal(CopilotToolExecutionPhase.Completed, toolContent.Phase);
        Assert.Equal("call-1", toolContent.ToolCallId);
        Assert.True(toolContent.IsSuccess);
        Assert.Null(toolContent.ErrorMessage);
        Assert.Same(toolCompleteEvent, toolContent.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_Failure_EmitsErrorContent()
    {
        // Arrange
        var toolCompleteEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-1",
                Success = false,
                Error = new ToolExecutionCompleteError { Message = "Build failed" }
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-id", tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(toolCompleteEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var toolContent = Assert.IsType<CopilotToolExecutionContent>(content);
        Assert.Equal(CopilotToolExecutionPhase.Completed, toolContent.Phase);
        Assert.False(toolContent.IsSuccess);
        Assert.Equal("Build failed", toolContent.ErrorMessage);
    }
}
