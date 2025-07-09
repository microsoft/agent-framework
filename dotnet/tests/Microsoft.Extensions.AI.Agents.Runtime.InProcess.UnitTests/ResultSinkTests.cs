// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using System.Threading.Tasks.Sources;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class ResultSinkTests
{
    [Fact]
    public void GetResultTest()
    {
        // Arrange
        ResultSink<int> sink = new();
        const int ExpectedResult = 42;

        // Act
        sink.SetResult(ExpectedResult);
        int result = sink.GetResult(0);

        // Assert
        Assert.Equal(ExpectedResult, result);
        Assert.Equal(ValueTaskSourceStatus.Succeeded, sink.GetStatus(0));
    }

    [Fact]
    public async Task FutureResultTestAsync()
    {
        // Arrange
        ResultSink<string> sink = new();
        const string ExpectedResult = "test";

        // Act
        sink.SetResult(ExpectedResult);
        string result = await sink.Future;

        // Assert
        Assert.Equal(ExpectedResult, result);
        Assert.Equal(ValueTaskSourceStatus.Succeeded, sink.GetStatus(0));
    }

    [Fact]
    public async Task SetExceptionTestAsync()
    {
        // Arrange
        ResultSink<int> sink = new();
        InvalidOperationException expectedException = new("Test exception");

        // Act
        sink.SetException(expectedException);

        // Assert
        Exception exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await sink.Future);
        Assert.Equal(expectedException.Message, exception.Message);
        exception = Assert.Throws<InvalidOperationException>(() => sink.GetResult(0));
        Assert.Equal(expectedException.Message, exception.Message);
        Assert.Equal(ValueTaskSourceStatus.Faulted, sink.GetStatus(0));
    }

    [Fact]
    public async Task SetCancelledTestAsync()
    {
        // Arrange
        ResultSink<int> sink = new();

        // Act
        sink.SetCancelled();

        // Assert
        Assert.True(sink.IsCancelled);
        Assert.Throws<OperationCanceledException>(() => sink.GetResult(0));
        await Assert.ThrowsAsync<OperationCanceledException>(async () => await sink.Future);
        Assert.Equal(ValueTaskSourceStatus.Canceled, sink.GetStatus(0));
    }

    [Fact]
    public void OnCompletedTest()
    {
        // Arrange
        ResultSink<int> sink = new();
        bool continuationCalled = false;
        const int ExpectedResult = 42;

        // Register the continuation
        sink.OnCompleted(
            state => continuationCalled = true,
            state: null,
            token: 0,
            ValueTaskSourceOnCompletedFlags.None);

        // Assert
        Assert.False(continuationCalled, "Continuation should have been called");

        // Act
        sink.SetResult(ExpectedResult);

        // Assert
        Assert.Equal(ExpectedResult, sink.GetResult(0));
        Assert.Equal(ValueTaskSourceStatus.Succeeded, sink.GetStatus(0));
        Assert.True(continuationCalled, "Continuation should have been called");
    }
}
