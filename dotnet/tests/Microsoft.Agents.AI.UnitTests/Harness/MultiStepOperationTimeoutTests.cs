// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.Harness;

public sealed class MultiStepOperationTimeoutTests
{
    [Fact]
    public async Task RunStep_CompletedStepDoesNotResetTimeoutAsync()
    {
        // Arrange
        using var timeout = new MultiStepOperationTimeout(TimeSpan.FromMilliseconds(100), CancellationToken.None);

        // Act
        int firstResult = timeout.RunStep(_ => 1);
        await Task.Delay(200);

        // Assert
        Assert.Equal(1, firstResult);
        Assert.Throws<TimeoutException>(() => timeout.RunStep(_ => 2));
    }

    [Fact]
    public async Task RunStepAsync_OperationIgnoresToken_ThrowsTimeoutExceptionAsync()
    {
        // Arrange
        using var timeout = new MultiStepOperationTimeout(TimeSpan.FromMilliseconds(50), CancellationToken.None);
        var pending = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);

        // Act + Assert
        await Assert.ThrowsAsync<TimeoutException>(() => timeout.RunStepAsync(_ => pending.Task));
    }

    [Fact]
    public async Task RunStepAsync_CallerCancels_ThrowsOperationCanceledExceptionAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        using var timeout = new MultiStepOperationTimeout(TimeSpan.FromSeconds(5), cts.Token);
        var pending = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string> operation = timeout.RunStepAsync(_ => pending.Task);

        // Act
        cts.Cancel();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => operation);
    }
}
