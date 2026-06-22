// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
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
    public async Task Constructor_WithApprovalRequiredTool_GatesExecutionAndDeniesWithoutCallbackAsync()
    {
        // Arrange
        bool invoked = false;
        AIFunction dangerousTool = AIFunctionFactory.Create(
            () => { invoked = true; return "sensitive operation completed"; },
            "ApprovalRequiredOperation",
            "Performs an approval-required operation.");
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool]);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);
        object? result = await exposedTool.InvokeAsync(new AIFunctionArguments());

        // Assert - the provider must NOT expose the same directly-invokable approval-required object,
        // and invoking the gate without an approval callback must deny execution.
        Assert.NotSame(approvalRequiredTool, exposedTool);
        Assert.False(invoked);
        Assert.Contains("requires human approval", result?.ToString());
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredTool_ExecutesWhenCallbackApprovesAsync()
    {
        // Arrange
        bool invoked = false;
        AIFunction dangerousTool = AIFunctionFactory.Create(
            () => { invoked = true; return "sensitive operation completed"; },
            "ApprovalRequiredOperation",
            "Performs an approval-required operation.");
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        FunctionCallContent? observedRequest = null;
        ValueTask<bool> approveAsync(FunctionCallContent request, CancellationToken _) { observedRequest = request; return new(true); }

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool], onFunctionApproval: approveAsync);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);
        object? result = await exposedTool.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.True(invoked);
        Assert.NotNull(observedRequest);
        Assert.Equal("ApprovalRequiredOperation", observedRequest!.Name);
        Assert.Contains("sensitive operation completed", result?.ToString());
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredTool_DeniesWhenCallbackRejectsAsync()
    {
        // Arrange
        bool invoked = false;
        AIFunction dangerousTool = AIFunctionFactory.Create(
            () => { invoked = true; return "sensitive operation completed"; },
            "ApprovalRequiredOperation",
            "Performs an approval-required operation.");
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        ValueTask<bool> denyAsync(FunctionCallContent request, CancellationToken cancellationToken) => new(false);

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool], onFunctionApproval: denyAsync);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);
        object? result = await exposedTool.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.False(invoked);
        Assert.Contains("the request was denied", result?.ToString());
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredTool_DeniesWhenCallbackThrowsAsync()
    {
        // Arrange
        bool invoked = false;
        AIFunction dangerousTool = AIFunctionFactory.Create(
            () => { invoked = true; return "sensitive operation completed"; },
            "ApprovalRequiredOperation",
            "Performs an approval-required operation.");
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        ValueTask<bool> throwingAsync(FunctionCallContent request, CancellationToken cancellationToken) => throw new InvalidOperationException("callback failure");

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool], onFunctionApproval: throwingAsync);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);
        object? result = await exposedTool.InvokeAsync(new AIFunctionArguments());

        // Assert - secure-by-default: a throwing callback denies execution rather than propagating.
        Assert.False(invoked);
        Assert.Contains("the request was denied", result?.ToString());
    }

    [Fact]
    public async Task Constructor_WithApprovalRequiredTool_PropagatesCancellationAsync()
    {
        // Arrange
        bool invoked = false;
        AIFunction dangerousTool = AIFunctionFactory.Create(
            () => { invoked = true; return "sensitive operation completed"; },
            "ApprovalRequiredOperation",
            "Performs an approval-required operation.");
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        ValueTask<bool> cancelingAsync(FunctionCallContent request, CancellationToken cancellationToken)
            => throw new OperationCanceledException(cancellationToken);

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool], onFunctionApproval: cancelingAsync);

        // Act & Assert - cancellation must propagate rather than being swallowed into a denial.
        AIFunction exposedTool = GetExposedFunction(agent);
        await Assert.ThrowsAsync<OperationCanceledException>(
            async () => await exposedTool.InvokeAsync(new AIFunctionArguments()));
        Assert.False(invoked);
    }

    [Fact]
    public void Constructor_WithApprovalRequiredTool_PreservesSkipPermissionMetadata()
    {
        // Arrange
        AIFunction dangerousTool = CopilotTool.DefineTool(
            () => "ok",
            toolOptions: new CopilotToolOptions { SkipPermission = true },
            factoryOptions: new AIFunctionFactoryOptions
            {
                Name = "WriteSensitiveMarker",
                Description = "Writes a sensitive marker file."
            });
        ApprovalRequiredAIFunction approvalRequiredTool = new(dangerousTool);

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [approvalRequiredTool]);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);

        // Assert - the gate must remain transparent to the Copilot SDK, preserving the skip_permission flag.
        Assert.NotSame(approvalRequiredTool, exposedTool);
        Assert.Equal("WriteSensitiveMarker", exposedTool.Name);
        Assert.NotNull(exposedTool.AdditionalProperties);
        Assert.True(exposedTool.AdditionalProperties.TryGetValue("skip_permission", out object? skip));
        Assert.Equal(true, skip);
    }

    [Fact]
    public void Constructor_WithNonApprovalTool_LeavesToolUnchanged()
    {
        // Arrange
        AIFunction plainTool = AIFunctionFactory.Create(() => "test", "TestFunc", "Test function");

        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, tools: [plainTool]);

        // Act
        AIFunction exposedTool = GetExposedFunction(agent);

        // Assert - tools that do not require approval pass through untouched.
        Assert.Same(plainTool, exposedTool);
    }

    private static AIFunction GetExposedFunction(GitHubCopilotAgent agent)
    {
        SessionConfig sessionConfig = GetSessionConfigFromAgent(agent);
        AIFunctionDeclaration declaration = Assert.Single(sessionConfig.Tools!);
        return declaration.GetService<AIFunction>()!;
    }

    private static SessionConfig GetSessionConfigFromAgent(GitHubCopilotAgent agent)
    {
        System.Reflection.FieldInfo field = typeof(GitHubCopilotAgent).GetField(
            "_sessionConfig",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        return (SessionConfig)field.GetValue(agent)!;
    }
}
