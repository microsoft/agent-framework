// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Tests verifying that ToolExecutionStartEvent and ToolExecutionCompleteEvent are correctly
/// projected into FunctionCallContent and FunctionResultContent respectively.
/// </summary>
public sealed class ToolExecutionEventProjectionTests
{
    [Fact]
    public void ToolExecutionStartEvent_ProducesFunctionCallContent()
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call_abc123",
                ToolName = "msgraph-admin__get_users",
                Arguments = "{\"top\": 10}",
                McpServerName = "msgraph-admin",
                McpToolName = "get_users"
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolStartEvent);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Contents);
        Assert.Equal(ChatRole.Assistant, result.Role);

        var content = Assert.IsType<FunctionCallContent>(result.Contents[0]);
        Assert.Equal("call_abc123", content.CallId);
        Assert.Equal("msgraph-admin__get_users", content.Name);
        Assert.NotNull(content.Arguments);
        Assert.Equal(10.0, content.Arguments["top"]);
        Assert.Same(toolStartEvent, content.RawRepresentation);
    }

    [Fact]
    public void ToolExecutionStartEvent_WithNullArguments_ProducesFunctionCallContentWithNullArguments()
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call_noargs",
                ToolName = "ping"
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolStartEvent);

        // Assert
        var content = Assert.IsType<FunctionCallContent>(result.Contents[0]);
        Assert.Equal("call_noargs", content.CallId);
        Assert.Equal("ping", content.Name);
        Assert.Null(content.Arguments);
    }

    [Fact]
    public void ToolExecutionCompleteEvent_Success_ProducesFunctionResultContent()
    {
        // Arrange
        var toolCompleteEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call_abc123",
                Success = true,
                Result = new ToolExecutionCompleteResult
                {
                    Content = "{\"users\":[{\"displayName\":\"Alice\",\"mail\":\"alice@contoso.com\"}]}"
                }
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolCompleteEvent);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Contents);
        Assert.Equal(ChatRole.Tool, result.Role);

        var content = Assert.IsType<FunctionResultContent>(result.Contents[0]);
        Assert.Equal("call_abc123", content.CallId);
        Assert.Same(toolCompleteEvent, content.RawRepresentation);
    }

    [Fact]
    public void ToolExecutionCompleteEvent_Error_ProducesFunctionResultContentWithErrorMessage()
    {
        // Arrange
        var toolCompleteEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call_def456",
                Success = false,
                Error = new ToolExecutionCompleteError
                {
                    Message = "Permission denied: insufficient scope for users.read"
                }
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolCompleteEvent);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Contents);
        Assert.Equal(ChatRole.Tool, result.Role);

        var content = Assert.IsType<FunctionResultContent>(result.Contents[0]);
        Assert.Equal("call_def456", content.CallId);
    }

    [Fact]
    public void ToolExecutionStartEvent_ParsesComplexArguments()
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call_complex",
                ToolName = "sn-query-table__getIncidents",
                Arguments = "{\"filter\": \"state=1\", \"limit\": 50, \"active\": true}"
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolStartEvent);

        // Assert
        var content = Assert.IsType<FunctionCallContent>(result.Contents[0]);
        Assert.Equal(50.0, content.Arguments!["limit"]);
        Assert.Equal(true, content.Arguments!["active"]);
    }

    [Fact]
    public void ToolExecutionCompleteEvent_NullData_ProducesFunctionResultContentWithDefaults()
    {
        // Arrange
        var toolCompleteEvent = new ToolExecutionCompleteEvent
        {
            Data = null!
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolCompleteEvent);

        // Assert
        var content = Assert.IsType<FunctionResultContent>(result.Contents[0]);
        Assert.Equal(string.Empty, content.CallId);
        Assert.Null(content.Result);
    }

    [Theory]
    [InlineData("null")]
    [InlineData("[1, 2, 3]")]
    [InlineData("\"just a string\"")]
    public void ToolExecutionStartEvent_NonObjectArguments_FallsBackToRawDictionary(string arguments)
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call_nonobj",
                ToolName = "some_tool",
                Arguments = arguments
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolStartEvent);

        // Assert
        var content = Assert.IsType<FunctionCallContent>(result.Contents[0]);
        Assert.NotNull(content.Arguments);
        Assert.Equal(arguments, content.Arguments["_raw"]);
    }

    [Fact]
    public void ToolExecutionStartEvent_MalformedJson_FallsBackToRawDictionary()
    {
        // Arrange
        var toolStartEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call_malformed",
                ToolName = "some_tool",
                Arguments = "{not valid json"
            }
        };

        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "test-agent", tools: null);

        // Act
        AgentResponseUpdate result = InvokeConvert(agent, toolStartEvent);

        // Assert
        var content = Assert.IsType<FunctionCallContent>(result.Contents[0]);
        Assert.NotNull(content.Arguments);
        Assert.Equal("{not valid json", content.Arguments["_raw"]);
    }

    /// <summary>
    /// Invokes the appropriate ConvertToAgentResponseUpdate method via reflection.
    /// </summary>
    private static AgentResponseUpdate InvokeConvert(GitHubCopilotAgent agent, SessionEvent sessionEvent)
    {
        MethodInfo? method = typeof(GitHubCopilotAgent)
            .GetMethod(
                "ConvertToAgentResponseUpdate",
                BindingFlags.Instance | BindingFlags.NonPublic,
                null,
                [sessionEvent.GetType()],
                null);

        // Fall back to the SessionEvent overload if no specific overload exists
        method ??= typeof(GitHubCopilotAgent)
            .GetMethod(
                "ConvertToAgentResponseUpdate",
                BindingFlags.Instance | BindingFlags.NonPublic,
                null,
                [typeof(SessionEvent)],
                null);

        Assert.NotNull(method);

        return (AgentResponseUpdate)method!.Invoke(agent, [sessionEvent])!;
    }
}
