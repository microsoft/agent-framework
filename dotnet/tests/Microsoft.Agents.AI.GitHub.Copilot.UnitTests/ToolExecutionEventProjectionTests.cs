// Copyright (c) Microsoft. All rights reserved.

using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for tool execution event projection in <see cref="GitHubCopilotAgent"/>.
/// </summary>
public sealed class ToolExecutionEventProjectionTests
{
    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_ProducesFunctionCallContent()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-1", tools: null);

        var startEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-123",
                ToolName = "readFile",
                Arguments = "{\"path\":\"/tmp/test.txt\"}"
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(startEvent);

        // Assert
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal("agent-1", result.AgentId);

        var content = Assert.Single(result.Contents);
        var functionCall = Assert.IsType<FunctionCallContent>(content);
        Assert.Equal("call-123", functionCall.CallId);
        Assert.Equal("readFile", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("/tmp/test.txt", functionCall.Arguments!["path"]?.ToString());
        Assert.Same(startEvent, functionCall.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_WithNullArguments_ProducesNullArguments()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var startEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-456",
                ToolName = "listTools",
                Arguments = null
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(startEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionCall = Assert.IsType<FunctionCallContent>(content);
        Assert.Equal("call-456", functionCall.CallId);
        Assert.Equal("listTools", functionCall.Name);
        Assert.Null(functionCall.Arguments);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_WithNullData_ProducesEmptyFunctionCall()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var startEvent = new ToolExecutionStartEvent { Data = null! };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(startEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionCall = Assert.IsType<FunctionCallContent>(content);
        Assert.Equal(string.Empty, functionCall.CallId);
        Assert.Equal(string.Empty, functionCall.Name);
        Assert.Null(functionCall.Arguments);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_WithSuccess_ProducesFunctionResultContent()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, id: "agent-2", tools: null);

        var completeEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-123",
                Success = true,
                Result = new ToolExecutionCompleteResult
                {
                    Content = "{\"users\":[{\"name\":\"Alice\"}]}"
                }
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(completeEvent);

        // Assert
        Assert.Equal(ChatRole.Tool, result.Role);
        Assert.Equal("agent-2", result.AgentId);

        var content = Assert.Single(result.Contents);
        var functionResult = Assert.IsType<FunctionResultContent>(content);
        Assert.Equal("call-123", functionResult.CallId);
        Assert.Equal("{\"users\":[{\"name\":\"Alice\"}]}", functionResult.Result);
        Assert.Same(completeEvent, functionResult.RawRepresentation);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_WithError_ProducesErrorResult()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var completeEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-789",
                Success = false,
                Error = new ToolExecutionCompleteError
                {
                    Code = "PERMISSION_DENIED",
                    Message = "Access denied to resource"
                }
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(completeEvent);

        // Assert
        Assert.Equal(ChatRole.Tool, result.Role);

        var content = Assert.Single(result.Contents);
        var functionResult = Assert.IsType<FunctionResultContent>(content);
        Assert.Equal("call-789", functionResult.CallId);
        Assert.Equal("Access denied to resource", functionResult.Result);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_WithFailureNoError_ProducesDefaultErrorMessage()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var completeEvent = new ToolExecutionCompleteEvent
        {
            Data = new ToolExecutionCompleteData
            {
                ToolCallId = "call-000",
                Success = false,
                Error = null
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(completeEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionResult = Assert.IsType<FunctionResultContent>(content);
        Assert.Equal("call-000", functionResult.CallId);
        Assert.Equal("Tool execution failed", functionResult.Result);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionCompleteEvent_WithNullData_ProducesEmptyResult()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var completeEvent = new ToolExecutionCompleteEvent { Data = null! };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(completeEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionResult = Assert.IsType<FunctionResultContent>(content);
        Assert.Equal(string.Empty, functionResult.CallId);
        Assert.Equal("Tool execution failed", functionResult.Result);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_WithInvalidJson_WrapsAsValue()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var startEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-bad",
                ToolName = "tool",
                Arguments = "not valid json"
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(startEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionCall = Assert.IsType<FunctionCallContent>(content);
        Assert.Equal("call-bad", functionCall.CallId);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("not valid json", functionCall.Arguments!["value"]);
    }

    [Fact]
    public void ConvertToAgentResponseUpdate_ToolExecutionStartEvent_WithMultipleArguments_ParsesAll()
    {
        // Arrange
        var copilotClient = new CopilotClient(new CopilotClientOptions { AutoStart = false });
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);

        var startEvent = new ToolExecutionStartEvent
        {
            Data = new ToolExecutionStartData
            {
                ToolCallId = "call-multi",
                ToolName = "queryTable",
                Arguments = "{\"table\":\"incidents\",\"limit\":10,\"filter\":\"active=true\"}"
            }
        };

        // Act
        AgentResponseUpdate result = agent.ConvertToAgentResponseUpdate(startEvent);

        // Assert
        var content = Assert.Single(result.Contents);
        var functionCall = Assert.IsType<FunctionCallContent>(content);
        Assert.Equal("call-multi", functionCall.CallId);
        Assert.Equal("queryTable", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("incidents", functionCall.Arguments!["table"]?.ToString());
        Assert.Equal("10", functionCall.Arguments!["limit"]?.ToString());
        Assert.Equal("active=true", functionCall.Arguments!["filter"]?.ToString());
    }
}
