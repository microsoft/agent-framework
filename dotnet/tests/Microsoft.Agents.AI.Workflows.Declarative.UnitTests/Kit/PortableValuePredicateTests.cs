// Copyright (c) Microsoft. All rights reserved.

using FluentAssertions;
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
        actual.Should().BeSameAs(result);
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
        actual.ExecutorId.Should().Be("test-executor");
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
        InvokeAzureAgentExecutor.RequiresInput(request).Should().BeTrue();
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresInput_WithPortableValueWrappedRequest_ReturnsTrue()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");
        PortableValue wrapped = new(request);

        // Act & Assert
        InvokeAzureAgentExecutor.RequiresInput(wrapped).Should().BeTrue();
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresInput_WithActionExecutorResult_ReturnsFalse()
    {
        // Arrange
        ActionExecutorResult result = new("test");

        // Act & Assert
        InvokeAzureAgentExecutor.RequiresInput(result).Should().BeFalse();
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithDirectActionExecutorResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");

        // Act & Assert
        InvokeAzureAgentExecutor.RequiresNothing(result).Should().BeTrue();
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithPortableValueWrappedResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");
        PortableValue wrapped = new(result);

        // Act & Assert
        InvokeAzureAgentExecutor.RequiresNothing(wrapped).Should().BeTrue();
    }

    [Fact]
    public void InvokeAzureAgentExecutor_RequiresNothing_WithExternalInputRequest_ReturnsFalse()
    {
        // Arrange
        ExternalInputRequest request = new("test prompt");

        // Act & Assert
        InvokeAzureAgentExecutor.RequiresNothing(request).Should().BeFalse();
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
        InvokeMcpToolExecutor.RequiresInput(wrapped).Should().BeTrue();
    }

    [Fact]
    public void InvokeMcpToolExecutor_RequiresNothing_WithPortableValueWrappedResult_ReturnsTrue()
    {
        // Arrange
        ActionExecutorResult result = new("test");
        PortableValue wrapped = new(result);

        // Act & Assert
        InvokeMcpToolExecutor.RequiresNothing(wrapped).Should().BeTrue();
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
        QuestionExecutor.IsComplete(wrapped).Should().BeTrue();
    }

    [Fact]
    public void QuestionExecutor_IsComplete_WithPortableValueWrappedResult_NonNullResult_ReturnsFalse()
    {
        // Arrange - result with non-null Result property means "not complete"
        ActionExecutorResult result = new("test", result: true);
        PortableValue wrapped = new(result);

        // Act & Assert
        QuestionExecutor.IsComplete(wrapped).Should().BeFalse();
    }

    #endregion
}
