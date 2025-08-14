// Copyright (c) Microsoft. All rights reserved.

using System;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests declarative workflow exceptions.
/// </summary>
public sealed class DeclarativeWorkflowExceptionTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public void InvalidScopeException()
    {
        AssertDefault<InvalidScopeException>(() => throw new InvalidScopeException());
        AssertMessage<InvalidScopeException>((message) => throw new InvalidScopeException(message));
        AssertInner<InvalidScopeException>((message, inner) => throw new InvalidScopeException(message, inner));
    }

    [Fact]
    public void InvalidSegmentException()
    {
        AssertDefault<InvalidSegmentException>(() => throw new InvalidSegmentException());
        AssertMessage<InvalidSegmentException>((message) => throw new InvalidSegmentException(message));
        AssertInner<InvalidSegmentException>((message, inner) => throw new InvalidSegmentException(message, inner));
    }

    [Fact]
    public void UnknownActionException()
    {
        AssertDefault<UnknownActionException>(() => throw new UnknownActionException());
        AssertMessage<UnknownActionException>((message) => throw new UnknownActionException(message));
        AssertInner<UnknownActionException>((message, inner) => throw new UnknownActionException(message, inner));
    }

    [Fact]
    public void UnknownDataTypeException()
    {
        AssertDefault<UnknownDataTypeException>(() => throw new UnknownDataTypeException());
        AssertMessage<UnknownDataTypeException>((message) => throw new UnknownDataTypeException(message));
        AssertInner<UnknownDataTypeException>((message, inner) => throw new UnknownDataTypeException(message, inner));
    }

    [Fact]
    public void WorkflowExecutionException()
    {
        AssertDefault<WorkflowExecutionException>(() => throw new WorkflowExecutionException());
        AssertMessage<WorkflowExecutionException>((message) => throw new WorkflowExecutionException(message));
        AssertInner<WorkflowExecutionException>((message, inner) => throw new WorkflowExecutionException(message, inner));
    }

    [Fact]
    public void WorkflowModelException()
    {
        AssertDefault<WorkflowModelException>(() => throw new WorkflowModelException());
        AssertMessage<WorkflowModelException>((message) => throw new WorkflowModelException(message));
        AssertInner<WorkflowModelException>((message, inner) => throw new WorkflowModelException(message, inner));
    }

    private static void AssertDefault<TException>(Action throwAction) where TException : Exception
    {
        TException exception = Assert.Throws<TException>(() => throwAction.Invoke());
        Assert.NotEmpty(exception.Message);
        Assert.Null(exception.InnerException);
    }

    private static void AssertMessage<TException>(Action<string> throwAction) where TException : Exception
    {
        const string message = "Test exception message";
        TException exception = Assert.Throws<TException>(() => throwAction.Invoke(message));
        Assert.Equal(message, exception.Message);
        Assert.Null(exception.InnerException);
    }

    private static void AssertInner<TException>(Action<string, Exception> throwAction) where TException : Exception
    {
        const string message = "Test exception message";
        NotSupportedException innerException = new("Inner exception message");
        TException exception = Assert.Throws<TException>(() => throwAction.Invoke(message, innerException));
        Assert.Equal(message, exception.Message);
        Assert.Equal(innerException, exception.InnerException);
    }
}
