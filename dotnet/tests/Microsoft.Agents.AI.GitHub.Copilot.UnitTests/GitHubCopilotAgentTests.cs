// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
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
        var mcpServers = new Dictionary<string, object> { ["server1"] = new McpLocalServerConfig() };

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
        var mcpServers = new Dictionary<string, object> { ["server1"] = new McpLocalServerConfig() };

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
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: TestId, tools: null);
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(assistantMessage);

        // result.Text need to be empty because the content was already delivered via delta events, and we want to avoid emitting duplicate content in the response update.
        // The content should be delivered through TextContent in the Contents collection instead.
        Assert.Empty(result.Text);
        Assert.DoesNotContain(result.Contents, c => c is TextContent);
    }

    [Fact]
    public void ConvertToolStartToAgentResponseUpdate_WithMcpToolName_ReturnsFunctionCallContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        const string AgentId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: AgentId, tools: null);
        var timestamp = DateTimeOffset.UtcNow;
        var toolStart = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-123",
                ToolName = "fallback_tool",
                McpToolName = "mcp_tool",
                Arguments = JsonSerializer.SerializeToElement(new { param1 = "value1", count = 42 })
            },
            Timestamp = timestamp
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolStartToAgentResponseUpdate(toolStart);

        // Assert
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal(AgentId, result.AgentId);
        Assert.Equal("call-123", result.MessageId);
        Assert.Equal(timestamp, result.CreatedAt);
        FunctionCallContent content = Assert.IsType<FunctionCallContent>(Assert.Single(result.Contents));
        Assert.Equal("call-123", content.CallId);
        Assert.Equal("mcp_tool", content.Name);
        Assert.NotNull(content.Arguments);
        Assert.Equal("value1", content.Arguments["param1"]);
        Assert.Equal(42L, content.Arguments["count"]);
        Assert.Same(toolStart, content.RawRepresentation);
    }

    [Fact]
    public void ConvertToolStartToAgentResponseUpdate_WithToolNameFallback_UsesToolName()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolStart = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-456",
                ToolName = "local_tool",
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolStartToAgentResponseUpdate(toolStart);

        // Assert
        FunctionCallContent content = Assert.IsType<FunctionCallContent>(Assert.Single(result.Contents));
        Assert.Equal("local_tool", content.Name);
        Assert.Null(content.Arguments);
    }

    [Fact]
    public void ConvertToolStartToAgentResponseUpdate_WithNonObjectJsonArguments_ReturnsNullArguments()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolStart = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-789",
                ToolName = "some_tool",
                Arguments = JsonSerializer.SerializeToElement("just a string")
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolStartToAgentResponseUpdate(toolStart);

        // Assert
        FunctionCallContent content = Assert.IsType<FunctionCallContent>(Assert.Single(result.Contents));
        Assert.Null(content.Arguments);
    }

    [Fact]
    public void ConvertToolStartToAgentResponseUpdate_WithAllJsonValueKinds_ConvertsCorrectly()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolStart = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-kinds",
                ToolName = "multi_type_tool",
                Arguments = JsonSerializer.SerializeToElement(new
                {
                    strVal = "hello",
                    boolTrue = true,
                    boolFalse = false,
                    nullVal = (string?)null,
                    intVal = 100,
                    floatVal = 3.14,
                    objVal = new { nested = "value" }
                })
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolStartToAgentResponseUpdate(toolStart);

        // Assert
        FunctionCallContent content = Assert.IsType<FunctionCallContent>(Assert.Single(result.Contents));
        Assert.NotNull(content.Arguments);
        Assert.Equal("hello", content.Arguments["strVal"]);
        Assert.Equal(true, content.Arguments["boolTrue"]);
        Assert.Equal(false, content.Arguments["boolFalse"]);
        Assert.Null(content.Arguments["nullVal"]);
        Assert.Equal(100L, content.Arguments["intVal"]);
        Assert.Equal(3.14, (double)content.Arguments["floatVal"]!, 2);
        // Non-primitive values fall back to raw JSON text
        Assert.IsType<string>(content.Arguments["objVal"]);
    }

    [Fact]
    public void ConvertToolCompleteToAgentResponseUpdate_WithResult_ReturnsFunctionResultContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        const string AgentId = "agent-id";
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: AgentId, tools: null);
        var timestamp = DateTimeOffset.UtcNow;
        var toolComplete = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-123",
                Success = true,
                Result = new ToolExecutionCompleteDataResult { Content = "tool output" }
            },
            Timestamp = timestamp
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolCompleteToAgentResponseUpdate(toolComplete);

        // Assert
        Assert.Equal(ChatRole.Tool, result.Role);
        Assert.Equal(AgentId, result.AgentId);
        Assert.Equal("call-123", result.MessageId);
        Assert.Equal(timestamp, result.CreatedAt);
        FunctionResultContent content = Assert.IsType<FunctionResultContent>(Assert.Single(result.Contents));
        Assert.Equal("call-123", content.CallId);
        Assert.Equal("tool output", content.Result);
        Assert.Same(toolComplete, content.RawRepresentation);
    }

    [Fact]
    public void ConvertToolCompleteToAgentResponseUpdate_WithError_ReturnsErrorMessage()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolComplete = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-err",
                Success = false,
                Error = new ToolExecutionCompleteDataError { Message = "Something went wrong" }
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolCompleteToAgentResponseUpdate(toolComplete);

        // Assert
        FunctionResultContent content = Assert.IsType<FunctionResultContent>(Assert.Single(result.Contents));
        Assert.Equal("call-err", content.CallId);
        Assert.Equal("Something went wrong", content.Result);
    }

    [Fact]
    public void ConvertToolCompleteToAgentResponseUpdate_ResultTakesPrecedenceOverError()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolComplete = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-both",
                Success = true,
                Result = new ToolExecutionCompleteDataResult { Content = "actual result" },
                Error = new ToolExecutionCompleteDataError { Message = "should be ignored" }
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolCompleteToAgentResponseUpdate(toolComplete);

        // Assert
        FunctionResultContent content = Assert.IsType<FunctionResultContent>(Assert.Single(result.Contents));
        Assert.Equal("actual result", content.Result);
    }

    [Fact]
    public void ConvertToolCompleteToAgentResponseUpdate_WithNoResultOrError_ReturnsNullResult()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        var toolComplete = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-empty",
                Success = true
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToolCompleteToAgentResponseUpdate(toolComplete);

        // Assert
        FunctionResultContent content = Assert.IsType<FunctionResultContent>(Assert.Single(result.Contents));
        Assert.Equal("call-empty", content.CallId);
        Assert.Null(content.Result);
    }
}
