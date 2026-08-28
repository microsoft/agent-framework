// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

/// <summary>
/// Tests that edge predicates correctly handle PortableValue-wrapped messages,
/// which occur after checkpoint restore (JSON round-trip).
/// </summary>
public sealed class PortableValuePredicateTests
{
    #region ActionExecutorResult.ThrowIfNot

    [Fact]
    public void ActionExecutorResult_ThrowIfNot_WithDirectActionExecutorResult_ReturnsResult()
    {
        // Arrange
        ActionExecutorResult result = new("test-executor");

        // Act
        ActionExecutorResult actual = ActionExecutorResult.ThrowIfNot(result);

        // Assert
        Assert.Same(result, actual);
    }

    [Fact]
    public void ActionExecutorResult_ThrowIfNot_WithPortableValueWrappedActionExecutorResult_Unwraps()
    {
        // Arrange
        ActionExecutorResult result = new("test-executor");
        PortableValue wrapped = new(result);

        // Act
        ActionExecutorResult actual = ActionExecutorResult.ThrowIfNot(wrapped);

        // Assert
        Assert.Equal("test-executor", actual.ExecutorId);
    }

    [Fact]
    public void ActionExecutorResult_ThrowIfNot_WithNonActionExecutorResult_Throws()
    {
        // Arrange
        object message = "not an ActionExecutorResult";

        // Act & Assert
        Assert.Throws<DeclarativeActionException>(() => ActionExecutorResult.ThrowIfNot(message));
    }

    [Fact]
    public void ActionExecutorResult_ThrowIfNot_WithNull_Throws()
    {
        // Act & Assert
        Assert.Throws<DeclarativeActionException>(() => ActionExecutorResult.ThrowIfNot(null));
    }

    [Fact]
    public void ActionExecutorResult_ThrowIfNot_WithPortableValueWrappedNonResult_Throws()
    {
        // Arrange
        PortableValue wrapped = new("not an ActionExecutorResult");

        // Act & Assert
        Assert.Throws<DeclarativeActionException>(() => ActionExecutorResult.ThrowIfNot(wrapped));
    }

    #endregion

    #region InvokeAzureAgentExecutor Predicates

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresInput_WithDirectExternalInputRequest_ReturnsTrue()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");

        // Act & Assert
        Assert.True(InvokeAzureAgentExecutor.RequiresInput(request));
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresInput_WithPortableValueWrappedRequest_ReturnsTrue()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");
        PortableValue wrapped = new(request);

        // Act & Assert
        Assert.True(InvokeAzureAgentExecutor.RequiresInput(wrapped));
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresInput_WithActionExecutorResult_ReturnsFalse()
    {
        // Arrange
        ActionExecutorResult result = new("test");

        // Act & Assert
        Assert.False(InvokeAzureAgentExecutor.RequiresInput(result));
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithDirectActionExecutorResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");

        // Act & Assert
        Assert.True(InvokeAzureAgentExecutor.RequiresNothing(result));
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithPortableValueWrappedResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");
        PortableValue wrapped = new(result);

        // Act & Assert
        Assert.True(InvokeAzureAgentExecutor.RequiresNothing(wrapped));
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithExternalInputRequest_ReturnsFalse()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");

        // Act & Assert
        Assert.False(InvokeAzureAgentExecutor.RequiresNothing(request));
    }

    #endregion

    #region InvokeMcpToolExecutor Predicates

    [Fact]
    public void InvokeMcpToolExecutor_RequiresInput_WithPortableValueWrappedRequest_ReturnsTrue()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");
        PortableValue wrapped = new(request);

        // Act & Assert
        Assert.True(InvokeMcpToolExecutor.RequiresInput(wrapped));
    }

    [Fact]
    public void InvokeMcpToolExecutor_RequiresNothing_WithPortableValueWrappedResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");
        PortableValue wrapped = new(result);

        // Act & Assert
        Assert.True(InvokeMcpToolExecutor.RequiresNothing(wrapped));
    }

    #endregion

    #region QuestionExecutor.IsComplete

    [Fact]
    public void QuestionExecutor_IsComplete_WithPortableValueWrappedResult_NullResult_ReturnsTrue()
    {
        // Arrange - result with null Result property means "complete"
        ActionExecutorResult result = new("test", result: null);
        PortableValue wrapped = new(result);

        // Act & Assert
        Assert.True(QuestionExecutor.IsComplete(wrapped));
    }

    [Fact]
    public void QuestionExecutor_IsComplete_WithPortableValueWrappedResult_NonNullResult_ReturnsFalse()
    {
        // Arrange - result with non-null Result property means "not complete"
        ActionExecutorResult result = new("test", result: true);
        PortableValue wrapped = new(result);

        // Act & Assert
        Assert.False(QuestionExecutor.IsComplete(wrapped));
    }

    #endregion
}
