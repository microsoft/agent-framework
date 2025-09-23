// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for AgentRunContext and AgentFunctionInvocationContext classes.
/// </summary>
public sealed class AgentFunctionInvocationContextTests
{
    /// <summary>
    /// Tests AgentFunctionInvocationContext constructor and property access.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Constructor_SetsPropertiesCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments { ["param"] = "value" };
        var cancellationToken = new CancellationToken();

        // Create a FunctionInvocationContext (this is typically created by the framework)
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };

        // Act
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, cancellationToken);

        // Assert
        Assert.Same(mockAgent.Object, context.Agent);
        Assert.Same(function, context.Function);
        Assert.Same(arguments, context.Arguments);
        Assert.Equal(cancellationToken, context.CancellationToken);
        Assert.Null(context.FunctionResult);
    }

    /// <summary>
    /// Tests AgentFunctionInvocationContext constructor with null agent throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };

        // Act & Assert
        Assert.Throws<ArgumentNullException>("agent", () =>
            new AgentFunctionInvocationContext(null!, functionInvocationContext, CancellationToken.None));
    }

    /// <summary>
    /// Tests that Function property can be modified.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Function_CanBeModified()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var originalFunction = AIFunctionFactory.Create(() => "result1", "Function1");
        var newFunction = AIFunctionFactory.Create(() => "result2", "Function2");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = originalFunction,
            Arguments = arguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);

        // Act
        context.Function = newFunction;

        // Assert
        Assert.Same(newFunction, context.Function);
        Assert.NotSame(originalFunction, context.Function);
    }

    /// <summary>
    /// Tests that Arguments property can be modified.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Arguments_CanBeModified()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var originalArguments = new AIFunctionArguments { ["param1"] = "value1" };
        var newArguments = new AIFunctionArguments { ["param2"] = "value2" };
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = originalArguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);

        // Act
        context.Arguments = newArguments;

        // Assert
        Assert.Same(newArguments, context.Arguments);
        Assert.NotSame(originalArguments, context.Arguments);
    }

    /// <summary>
    /// Tests that FunctionResult property can be set and retrieved.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_FunctionResult_CanBeSetAndRetrieved()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);
        const string ExpectedResult = "Test result";

        // Act
        context.FunctionResult = ExpectedResult;

        // Assert
        Assert.Equal(ExpectedResult, context.FunctionResult);
    }
}
