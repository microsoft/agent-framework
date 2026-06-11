// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AlwaysApproveToolApprovalResponseContent"/> class
/// and <see cref="ToolApprovalRequestContentExtensions"/> extension methods.
/// </summary>
public class AlwaysApproveToolApprovalResponseContentTests
{
    #region CreateAlwaysApproveToolResponse

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse sets AlwaysApproveTool to true.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_AlwaysApproveTool_IsTrue()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.True(result.AlwaysApproveTool);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse sets AlwaysApproveToolWithArguments to false.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_AlwaysApproveToolWithArguments_IsFalse()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.False(result.AlwaysApproveToolWithArguments);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse creates an approved inner response.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_InnerResponse_IsApproved()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.True(result.InnerResponse.Approved);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse forwards the reason.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_Reason_IsForwarded()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse("User trusts this tool");

        // Assert
        Assert.Equal("User trusts this tool", result.InnerResponse.Reason);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse preserves the request ID.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_RequestId_IsPreserved()
    {
        // Arrange
        var request = CreateRequest("MyTool", "custom-request-id");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.Equal("custom-request-id", result.InnerResponse.RequestId);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse preserves the tool call.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_ToolCall_IsPreserved()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        var functionCall = Assert.IsType<FunctionCallContent>(result.InnerResponse.ToolCall);
        Assert.Equal("MyTool", functionCall.Name);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse with null reason sets reason to null.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_NullReason_ReasonIsNull()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.Null(result.InnerResponse.Reason);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse throws on null request.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_NullRequest_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("request",
            () => ((ToolApprovalRequestContent)null!).CreateAlwaysApproveToolResponse());
    }

    #endregion

    #region CreateAlwaysApproveToolWithArgumentsResponse

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse sets AlwaysApproveToolWithArguments to true.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_AlwaysApproveToolWithArguments_IsTrue()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        Assert.True(result.AlwaysApproveToolWithArguments);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse sets AlwaysApproveTool to false.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_AlwaysApproveTool_IsFalse()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        Assert.False(result.AlwaysApproveTool);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse creates an approved inner response.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_InnerResponse_IsApproved()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        Assert.True(result.InnerResponse.Approved);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse forwards the reason.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_Reason_IsForwarded()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse("Specific approval");

        // Assert
        Assert.Equal("Specific approval", result.InnerResponse.Reason);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse throws on null request.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_NullRequest_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("request",
            () => ((ToolApprovalRequestContent)null!).CreateAlwaysApproveToolWithArgumentsResponse());
    }

    #endregion

    #region AlwaysApproveToolApprovalResponseContent Properties

    /// <summary>
    /// Verify that the content is an AIContent subclass.
    /// </summary>
    [Fact]
    public void Content_IsAIContentSubclass()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var result = request.CreateAlwaysApproveToolResponse();

        // Assert
        Assert.IsAssignableFrom<AIContent>(result);
    }

    /// <summary>
    /// Verify that InnerResponse preserves tool call arguments.
    /// </summary>
    [Fact]
    public void InnerResponse_PreservesArguments()
    {
        // Arrange
        var args = new Dictionary<string, object?> { ["path"] = "test.txt", ["count"] = 5 };
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "ReadFile", args));

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        var functionCall = Assert.IsType<FunctionCallContent>(result.InnerResponse.ToolCall);
        Assert.Equal(2, functionCall.Arguments!.Count);
        Assert.Equal("test.txt", functionCall.Arguments["path"]);
    }

    /// <summary>
    /// Verify that both factory methods produce distinct instances from the same request.
    /// </summary>
    [Fact]
    public void FactoryMethods_ProduceDistinctInstances()
    {
        // Arrange
        var request = CreateRequest("MyTool");

        // Act
        var toolLevel = request.CreateAlwaysApproveToolResponse();
        var argsLevel = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        Assert.NotSame(toolLevel, argsLevel);
        Assert.NotSame(toolLevel.InnerResponse, argsLevel.InnerResponse);
    }

    #endregion

    #region Helpers

    private static ToolApprovalRequestContent CreateRequest(string toolName, string requestId = "req1")
    {
        return new ToolApprovalRequestContent(requestId, new FunctionCallContent("call1", toolName));
    }

    #endregion
}
