// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using GitHub.Copilot;
using GitHub.Copilot.Rpc;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

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
        List<AIFunctionDeclaration> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
        Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> permissionHandler = (_, _) => Task.FromResult(PermissionDecision.ApproveOnce());
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
            ConfigDirectory = "/config",
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
        Assert.Equal(systemMessage, result.SystemMessage);
        Assert.Equal(new List<string> { "tool1", "tool2" }, result.AvailableTools);
        Assert.Equal(new List<string> { "tool3" }, result.ExcludedTools);
        Assert.Equal("/workspace", result.WorkingDirectory);
        Assert.Equal("/config", result.ConfigDirectory);
        Assert.Same(hooks, result.Hooks);
        Assert.Same(infiniteSessions, result.InfiniteSessions);
        Assert.Same(permissionHandler, result.OnPermissionRequest);
        Assert.Same(userInputHandler, result.OnUserInputRequest);
        Assert.Equal(new List<string> { "skill1" }, result.DisabledSkills);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_CopiesAllProperties()
    {
        // Arrange
        List<AIFunctionDeclaration> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];
        var hooks = new SessionHooks();
        var infiniteSessions = new InfiniteSessionConfig();
        var systemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = "Be helpful" };
        Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> permissionHandler = (_, _) => Task.FromResult(PermissionDecision.ApproveOnce());
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
            ConfigDirectory = "/config",
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
        Assert.Equal("/config", result.ConfigDirectory);
        Assert.Same(hooks, result.Hooks);
        Assert.Same(infiniteSessions, result.InfiniteSessions);
        Assert.Same(permissionHandler, result.OnPermissionRequest);
        Assert.Same(userInputHandler, result.OnUserInputRequest);
        Assert.Same(mcpServers, result.McpServers);
        Assert.Equal(new List<string> { "skill1" }, result.DisabledSkills);
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
        Assert.Null(result.ConfigDirectory);
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopySessionConfig_WithStreamingDisabled_PreservesStreamingValue()
    {
        // Arrange
        var source = new SessionConfig
        {
            Streaming = false,
            Model = "gpt-4o",
        };

        // Act
        SessionConfig result = GitHubCopilotAgent.CopySessionConfig(source);

        // Assert
        Assert.False(result.Streaming);
    }

    [Fact]
    public void CopySessionConfig_WithStreamingNull_DefaultsToTrue()
    {
        // Arrange
        var source = new SessionConfig
        {
            Model = "gpt-4o",
        };

        // Act
        SessionConfig result = GitHubCopilotAgent.CopySessionConfig(source);

        // Assert
        Assert.True(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_WithStreamingDisabled_PreservesStreamingValue()
    {
        // Arrange
        var source = new SessionConfig
        {
            Streaming = false,
            Model = "gpt-4o",
        };

        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(source);

        // Assert
        Assert.False(result.Streaming);
    }

    [Fact]
    public void CopyResumeSessionConfig_WithStreamingNull_DefaultsToTrue()
    {
        // Arrange
        var source = new SessionConfig
        {
            Model = "gpt-4o",
        };

        // Act
        ResumeSessionConfig result = GitHubCopilotAgent.CopyResumeSessionConfig(source);

        // Assert
        Assert.True(result.Streaming);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantMessageEventWhenStreaming_DoesNotEmitTextContent()
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
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage, isStreaming: true);

        // result.Text should be empty because content was already delivered via delta events.
        Assert.Empty(result.Text);
        Assert.DoesNotContain(result.Contents, c => c is TextContent);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantMessageEventWhenNotStreaming_EmitsTextContent()
    {
        // Arrange
        const string ExpectedContent = "Full response text from non-streaming session";
        var assistantMessage = new AssistantMessageEvent
        {
            Data = new AssistantMessageData
            {
                MessageId = "msg-789",
                Content = ExpectedContent
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        const string TestId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage, isStreaming: false);

        // Assert - text must be emitted since no delta events precede it in non-streaming mode.
        Assert.Equal(ExpectedContent, result.Text);
        Assert.Contains(result.Contents, c => c is TextContent);
        TextContent textContent = (TextContent)result.Contents.Single(c => c is TextContent);
        Assert.Equal(ExpectedContent, textContent.Text);
        Assert.Same(assistantMessage, textContent.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantMessageEventWhenNotStreaming_HandlesEmptyContent()
    {
        // Arrange
        var assistantMessage = new AssistantMessageEvent
        {
            Data = new AssistantMessageData
            {
                MessageId = "msg-000",
                Content = string.Empty
            }
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        const string TestId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage, isStreaming: false);

        // Assert - should emit empty TextContent rather than throwing.
        Assert.Empty(result.Text);
        Assert.Contains(result.Contents, c => c is TextContent);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_AssistantMessageEventWhenNotStreaming_HandlesNullData()
    {
        // Arrange
        var assistantMessage = new AssistantMessageEvent
        {
            Data = null!
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());
        const string TestId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, tools: null);

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage, isStreaming: false);

        // Assert - null Data should produce empty TextContent via null-propagation fallback.
        Assert.Empty(result.Text);
        Assert.Contains(result.Contents, c => c is TextContent);
        Assert.Null(result.MessageId);
        Assert.Null(result.ResponseId);
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredTool_InstallsAskPreToolUseHookAsync()
    {
        // Arrange
        AIFunction dangerousTool = AIFunctionFactory.Create(() => "sensitive", "ApprovalRequiredOperation", "A sensitive operation.");
        AIFunction plainTool = AIFunctionFactory.Create(() => "ok", "PlainOperation", "A normal operation.");
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, tools: [new ApprovalRequiredAIFunction(dangerousTool), plainTool]);

        // Assert - the provider installs a default OnPreToolUse that asks for the approval-required tool
        // (routing the decision to OnPermissionRequest) and defers everything else.
        SessionConfig sessionConfig = GetSessionConfigFromAgent(agent);
        Assert.NotNull(sessionConfig.Hooks?.OnPreToolUse);

        PreToolUseHookOutput? approvalDecision = await InvokePreToolUseAsync(sessionConfig, "ApprovalRequiredOperation");
        Assert.Equal("ask", approvalDecision?.PermissionDecision);
        Assert.False(string.IsNullOrEmpty(approvalDecision?.PermissionDecisionReason));

        PreToolUseHookOutput? plainDecision = await InvokePreToolUseAsync(sessionConfig, "PlainOperation");
        Assert.Null(plainDecision);
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredToolInSessionConfig_InstallsAskPreToolUseHookAsync()
    {
        // Arrange
        AIFunction dangerousTool = AIFunctionFactory.Create(() => "sensitive", "ApprovalRequiredOperation", "A sensitive operation.");
        SessionConfig sessionConfig = new() { Tools = [new ApprovalRequiredAIFunction(dangerousTool)] };
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, sessionConfig);

        // Assert
        SessionConfig configured = GetSessionConfigFromAgent(agent);
        Assert.NotNull(configured.Hooks?.OnPreToolUse);
        PreToolUseHookOutput? decision = await InvokePreToolUseAsync(configured, "ApprovalRequiredOperation");
        Assert.Equal("ask", decision?.PermissionDecision);
    }

    [Fact]
    public void Constructor_WithNoApprovalRequiredTools_DoesNotInstallPreToolUseHook()
    {
        // Arrange
        AIFunction plainTool = AIFunctionFactory.Create(() => "ok", "PlainOperation", "A normal operation.");
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, tools: [plainTool]);

        // Assert - no approval-required tools means no hook is installed; tools flow through normally.
        SessionConfig sessionConfig = GetSessionConfigFromAgent(agent);
        Assert.Null(sessionConfig.Hooks?.OnPreToolUse);
    }

    [Fact]
    public async Task Constructor_WithUserPreToolUseHook_PreservesItAndWarnsAsync()
    {
        // Arrange - the caller supplies their own OnPreToolUse hook and also registers an approval-required tool.
        AIFunction dangerousTool = AIFunctionFactory.Create(() => "sensitive", "ApprovalRequiredOperation", "A sensitive operation.");
        var userHookOutput = new PreToolUseHookOutput { PermissionDecision = "allow" };
        SessionConfig sessionConfig = new()
        {
            Tools = [new ApprovalRequiredAIFunction(dangerousTool)],
            Hooks = new SessionHooks
            {
                OnPreToolUse = (input, invocation) => Task.FromResult<PreToolUseHookOutput?>(userHookOutput),
            },
        };

        CapturingLoggerFactory loggerFactory = new();
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, sessionConfig, loggerFactory: loggerFactory);

        // Assert - the user's hook is preserved (not overridden), and a warning is logged for the unenforced tool.
        SessionConfig configured = GetSessionConfigFromAgent(agent);
        PreToolUseHookOutput? decision = await InvokePreToolUseAsync(configured, "ApprovalRequiredOperation");
        Assert.Same(userHookOutput, decision);

        (LogLevel Level, string Message) warning = Assert.Single(loggerFactory.Entries, e => e.Level == LogLevel.Warning);
        Assert.Contains("ApprovalRequiredOperation", warning.Message);
    }

    [Fact]
    public void Constructor_WithUserPreToolUseHookButNoApprovalRequiredTools_DoesNotWarn()
    {
        // Arrange
        AIFunction plainTool = AIFunctionFactory.Create(() => "ok", "PlainOperation", "A normal operation.");
        SessionConfig sessionConfig = new()
        {
            Tools = [plainTool],
            Hooks = new SessionHooks
            {
                OnPreToolUse = (input, invocation) => Task.FromResult<PreToolUseHookOutput?>(null),
            },
        };

        CapturingLoggerFactory loggerFactory = new();
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        var agent = new GitHubCopilotAgent(copilotClient, sessionConfig, loggerFactory: loggerFactory);

        // Assert - nothing is being bypassed, so no warning is emitted.
        Assert.DoesNotContain(loggerFactory.Entries, e => e.Level == LogLevel.Warning);
    }

    [Fact]
    public void Constructor_WithApprovalRequiredTool_DoesNotMutateCallerHooks()
    {
        // Arrange
        AIFunction dangerousTool = AIFunctionFactory.Create(() => "sensitive", "ApprovalRequiredOperation", "A sensitive operation.");
        SessionHooks callerHooks = new();
        SessionConfig sessionConfig = new()
        {
            Tools = [new ApprovalRequiredAIFunction(dangerousTool)],
            Hooks = callerHooks,
        };
        CopilotClient copilotClient = new(new CopilotClientOptions());

        // Act
        _ = new GitHubCopilotAgent(copilotClient, sessionConfig);

        // Assert - the caller-supplied SessionConfig and its Hooks instance are not mutated.
        Assert.Null(callerHooks.OnPreToolUse);
        Assert.Same(callerHooks, sessionConfig.Hooks);
    }

    private static Task<PreToolUseHookOutput?> InvokePreToolUseAsync(SessionConfig sessionConfig, string toolName)
    {
        var input = new PreToolUseHookInput { ToolName = toolName };
        return sessionConfig.Hooks!.OnPreToolUse!(input, new HookInvocation());
    }

    private static SessionConfig GetSessionConfigFromAgent(GitHubCopilotAgent agent)
    {
        System.Reflection.FieldInfo field = typeof(GitHubCopilotAgent).GetField(
            "_sessionConfig",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        return (SessionConfig)field.GetValue(agent)!;
    }

    private sealed class CapturingLoggerFactory : ILoggerFactory
    {
        public List<(LogLevel Level, string Message)> Entries { get; } = [];

        public void AddProvider(ILoggerProvider provider)
        {
        }

        public ILogger CreateLogger(string categoryName) => new CapturingLogger(this.Entries);

        public void Dispose()
        {
        }

        private sealed class CapturingLogger(List<(LogLevel Level, string Message)> entries) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

            public bool IsEnabled(LogLevel logLevel) => true;

            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
                => entries.Add((logLevel, formatter(state, exception)));
        }
    }
}
