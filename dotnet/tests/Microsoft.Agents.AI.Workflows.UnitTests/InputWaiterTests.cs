// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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
        signaled.Should().BeTrue("the already-signaled input should release the wait");
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_BlocksUntilSignaledAsync()
    {
        // Arrange - the no-timeout overload is used so that only SignalInput can release the wait.
        using CancellationTokenSource guard = new();
        Task waitTask = this._waiter.WaitForInputAsync(guard.Token);

        // Assert - the waiter stays blocked while no input has been signaled.
        Task completedBeforeSignal = await Task.WhenAny(waitTask, Task.Delay(100));
        completedBeforeSignal.Should().NotBeSameAs(
            waitTask,
            "the waiter should not complete before input is signaled");

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
        FluentActions.Invoking(() =>
        {
            this._waiter.SignalInput();
            this._waiter.SignalInput();
        }).Should().NotThrow("double signaling should be handled gracefully");
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_RespectsCancellationAsync()
    {
        using CancellationTokenSource cts = new();
        Task waitTask = this._waiter.WaitForInputAsync(cts.Token);

        cts.Cancel();

        Func<Task> act = () => waitTask;
        await act.Should().ThrowAsync<OperationCanceledException>();
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_DoesNotCompleteWhenNotSignaledAsync()
    {
        using CancellationTokenSource cts = new();
        Task waitTask = this._waiter.WaitForInputAsync(cts.Token);
        Task completed = await Task.WhenAny(waitTask, Task.Delay(100));

        completed.Should().NotBeSameAs(waitTask, "the wait task should not complete when input is not signaled");

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
        firstSignaled.Should().BeTrue("the first signal should release the first wait");
        secondSignaled.Should().BeTrue("the second signal should release the second wait");
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
        signaled.Should().BeFalse("the wait should be released by the expiring timeout rather than by a signal");
    }
}
