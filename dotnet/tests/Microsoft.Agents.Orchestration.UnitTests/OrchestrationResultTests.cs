// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Orchestration.UnitTest;

public class OrchestrationResultTests
{
    [Fact]
    public async Task ConstructorInitializesPropertiesCorrectlyAsync()
    {
        // Arrange
        OrchestrationContext context = new("TestOrchestration", new TopicId("testTopic"), null, null, NullLoggerFactory.Instance, CancellationToken.None);
        TaskCompletionSource<string> tcs = new();

        // Act
        using CancellationTokenSource cancelSource = new();
        await using OrchestrationResult<string> result = new(context, tcs, cancelSource, NullLogger.Instance);

        // Assert
        Assert.Equal("TestOrchestration", result.Orchestration);
        Assert.Equal(new TopicId("testTopic"), result.Topic);
    }

    [Fact]
    public async Task GetValueAsyncReturnsCompletedValueWhenTaskIsCompletedAsync()
    {
        // Arrange
        OrchestrationContext context = new("TestOrchestration", new TopicId("testTopic"), null, null, NullLoggerFactory.Instance, CancellationToken.None);
        TaskCompletionSource<string> tcs = new();
        using CancellationTokenSource cancelSource = new();
        await using OrchestrationResult<string> result = new(context, tcs, cancelSource, NullLogger.Instance);
        string expectedValue = "Result value";

        // Act
        tcs.SetResult(expectedValue);
        string actualValue = await result.Task;

        // Assert
        Assert.Equal(expectedValue, actualValue);
    }

    [Fact]
    public async Task GetValueAsyncReturnsCompletedValueWhenCompletionIsDelayedAsync()
    {
        // Arrange
        OrchestrationContext context = new("TestOrchestration", new TopicId("testTopic"), null, null, NullLoggerFactory.Instance, CancellationToken.None);
        TaskCompletionSource<int> tcs = new();
        using CancellationTokenSource cancelSource = new();
        await using OrchestrationResult<int> result = new(context, tcs, cancelSource, NullLogger.Instance);
        int expectedValue = 42;

        // Act
        // Simulate delayed completion in a separate task
        Task delayTask = Task.Run(async () =>
        {
            await Task.Delay(100);
            tcs.SetResult(expectedValue);
        });

        int actualValue = await result.Task;

        // Assert
        Assert.Equal(expectedValue, actualValue);
    }
}
