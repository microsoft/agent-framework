// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Runtime.InProcess.Tests;

[Trait("Category", "Unit")]
public class MessageDeliveryTests
{
    private static readonly Func<MessageEnvelope, CancellationToken, ValueTask> s_emptyServicer = (_, _) => new ValueTask();

    [Fact]
    public void ConstructorInitializesProperties()
    {
        // Arrange
        MessageEnvelope message = new(new object());
        ResultSink<object?> resultSink = new();

        // Act
        MessageDelivery delivery = new(message, s_emptyServicer, resultSink);

        // Assert
        Assert.Same(message, delivery.Message);
        Assert.Same(s_emptyServicer, delivery.Servicer);
        Assert.Same(resultSink, delivery.ResultSink);
    }

    [Fact]
    public async Task FutureWithResultSinkReturnsSinkFutureAsync()
    {
        // Arrange
        MessageEnvelope message = new(new object());

        ResultSink<object?> resultSink = new();
        int expectedResult = 42;
        resultSink.SetResult(expectedResult);

        // Act
        MessageDelivery delivery = new(message, s_emptyServicer, resultSink);
        object? result = await delivery.ResultSink.Future;

        // Assert
        Assert.Equal(expectedResult, result);
    }

    [Fact]
    public async Task InvokeCallsServicerWithCorrectParametersAsync()
    {
        // Arrange
        MessageEnvelope message = new(new object());
        CancellationToken cancellationToken = new();

        bool servicerCalled = false;
        MessageEnvelope? passedMessage = null;
        CancellationToken? passedToken = null;

        ValueTask servicer(MessageEnvelope msg, CancellationToken token)
        {
            servicerCalled = true;
            passedMessage = msg;
            passedToken = token;
            return ValueTask.CompletedTask;
        }

        ResultSink<object?> sink = new();
        MessageDelivery delivery = new(message, servicer, sink);

        // Act
        await delivery.InvokeAsync(cancellationToken);

        // Assert
        Assert.True(servicerCalled);
        Assert.Same(message, passedMessage);
        Assert.Equal(cancellationToken, passedToken);
    }
}
