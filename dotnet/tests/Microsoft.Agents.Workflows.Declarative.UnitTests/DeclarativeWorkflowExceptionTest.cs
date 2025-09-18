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
    public void WorkflowExecutionException()
    {
        AssertDefault<DeclarativeActionException>(() => throw new DeclarativeActionException());
        AssertMessage<DeclarativeActionException>((message) => throw new DeclarativeActionException(message));
        AssertInner<DeclarativeActionException>((message, inner) => throw new DeclarativeActionException(message, inner));
    }

    [Fact]
    public void WorkflowModelException()
    {
        AssertDefault<DeclarativeModelException>(() => throw new DeclarativeModelException());
        AssertMessage<DeclarativeModelException>((message) => throw new DeclarativeModelException(message));
        AssertInner<DeclarativeModelException>((message, inner) => throw new DeclarativeModelException(message, inner));
    }

    private static void AssertDefault<TException>(Action throwAction) where TException : Exception
    {
        TException exception = Assert.Throws<TException>(throwAction.Invoke);
        Assert.NotEmpty(exception.Message);
        Assert.Null(exception.InnerException);
    }

    private static void AssertMessage<TException>(Action<string> throwAction) where TException : Exception
    {
        const string Message = "Test exception message";
        TException exception = Assert.Throws<TException>(() => throwAction.Invoke(Message));
        Assert.Equal(Message, exception.Message);
        Assert.Null(exception.InnerException);
    }

    private static void AssertInner<TException>(Action<string, Exception> throwAction) where TException : Exception
    {
        const string Message = "Test exception message";
        NotSupportedException innerException = new("Inner exception message");
        TException exception = Assert.Throws<TException>(() => throwAction.Invoke(Message, innerException));
        Assert.Equal(Message, exception.Message);
        Assert.Equal(innerException, exception.InnerException);
    }
}
