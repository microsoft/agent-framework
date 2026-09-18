// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class InputWaiterTests : IDisposable
{
    /// <summary>
    /// Liveness backstop for waits that are expected to complete. Never the thing under test:
    /// it is set far above the timeouts being exercised so a regression fails instead of hanging.
    /// </summary>
    private static readonly TimeSpan s_guardTimeout = TimeSpan.FromSeconds(30);

    private readonly InputWaiter _waiter = new();

    public void Dispose()
    {
        this._waiter.Dispose();
        GC.SuppressFinalize(this);
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_CompletesAfterSignalAsync()
    {
        // Arrange
        this._waiter.SignalInput();

        // Act
        bool signaled = await this._waiter.WaitForInputAsync(s_guardTimeout);

        // Assert
        Assert.True(signaled);
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_BlocksUntilSignaledAsync()
    {
        // Arrange - the no-timeout overload is used so that only SignalInput can release the wait.
        using CancellationTokenSource guard = new();
        Task waitTask = this._waiter.WaitForInputAsync(guard.Token);

        // Assert - the waiter stays blocked while no input has been signaled.
        Task completedBeforeSignal = await Task.WhenAny(waitTask, Task.Delay(100));
        Assert.NotSame(waitTask, completedBeforeSignal);

        // Act
        this._waiter.SignalInput();

        // Armed only once the signal has released the wait, since cancelling a still-pending
        // waiter would fail the test rather than guard it.
        guard.CancelAfter(s_guardTimeout);

        // Assert - completion alone proves the signal released the wait.
        await waitTask;
    }

    [Fact]
    public void InputWaiter_SignalInput_DoubleSignalDoesNotThrow()
    {
        // Binary semaphore behavior: double signal should be idempotent
        Assert.Null(Record.Exception(() =>
        {
            this._waiter.SignalInput();
            this._waiter.SignalInput();
        }));
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_RespectsCancellationAsync()
    {
        using CancellationTokenSource cts = new();
        Task waitTask = this._waiter.WaitForInputAsync(cts.Token);

        cts.Cancel();

        Task actAsync() => waitTask;
        await Assert.ThrowsAsync<OperationCanceledException>(actAsync);
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_DoesNotCompleteWhenNotSignaledAsync()
    {
        using CancellationTokenSource cts = new();
        Task waitTask = this._waiter.WaitForInputAsync(cts.Token);
        Task completed = await Task.WhenAny(waitTask, Task.Delay(100));

        Assert.NotSame(waitTask, completed);

        // Cancel and observe the pending task to avoid an unobserved exception on Dispose
        cts.Cancel();
        try { await waitTask; }
        catch (OperationCanceledException) { }
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_CanBeSignaledMultipleTimesSequentiallyAsync()
    {
        // Arrange / Act - first signal/wait cycle
        this._waiter.SignalInput();
        bool firstSignaled = await this._waiter.WaitForInputAsync(s_guardTimeout);

        // Arrange / Act - second signal/wait cycle
        this._waiter.SignalInput();
        bool secondSignaled = await this._waiter.WaitForInputAsync(s_guardTimeout);

        // Assert each cycle was released by its signal rather than by an expiring timeout.
        Assert.True(firstSignaled);
        Assert.True(secondSignaled);
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_CompletesWhenTimeoutExpiresAsync()
    {
        // Arrange - nothing signals this waiter, so an expiring timeout is the only thing that
        // can release the wait, and the returned flag proves which one did. The guard only
        // bounds a wait that never returns; it is not part of the assertion.
        using CancellationTokenSource guard = new();

        // Act
        Task<bool> waitTask = this._waiter.WaitForInputAsync(TimeSpan.FromMilliseconds(300), guard.Token);
        guard.CancelAfter(s_guardTimeout);

        bool signaled = await waitTask;

        // Assert
        Assert.False(signaled);
    }
}
