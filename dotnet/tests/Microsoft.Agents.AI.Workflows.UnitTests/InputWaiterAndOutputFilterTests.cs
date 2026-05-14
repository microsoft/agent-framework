// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class InputWaiterTests : IDisposable
{
    private readonly InputWaiter _waiter = new();

    public void Dispose()
    {
        this._waiter.Dispose();
        GC.SuppressFinalize(this);
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_CompletesAfterSignalAsync()
    {
        this._waiter.SignalInput();

        // WaitForInputAsync should complete immediately since input was already signaled
        Task waitTask = this._waiter.WaitForInputAsync(CancellationToken.None);
        Task completed = await Task.WhenAny(waitTask, Task.Delay(TimeSpan.FromSeconds(1)));

        completed.Should().BeSameAs(waitTask, "the wait task should complete before the timeout");
        await waitTask;
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_BlocksUntilSignaledAsync()
    {
        // Use the no-timeout overload so that the wait can only be released by SignalInput.
        // A finite timeout would make this test's logic racy: the component correctly
        // honors the timeout, but if the test thread is starved of CPU time (CI load,
        // GC pause) long enough for the timeout to fire, waitTask completes before
        // SignalInput is called and the "should not complete before signaled" assertion
        // flakes. Timeout behavior is covered separately below.
        Task waitTask = this._waiter.WaitForInputAsync(CancellationToken.None);

        Task completedBeforeSignal = await Task.WhenAny(waitTask, Task.Delay(100));
        completedBeforeSignal.Should().NotBeSameAs(
            waitTask,
            "the waiter should not complete before input is signaled");

        this._waiter.SignalInput();

        Task completedAfterSignal = await Task.WhenAny(waitTask, Task.Delay(TimeSpan.FromSeconds(1)));
        completedAfterSignal.Should().BeSameAs(
            waitTask,
            "the wait task should complete after being signaled");

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
        // First signal/wait cycle
        this._waiter.SignalInput();
        await this._waiter.WaitForInputAsync(TimeSpan.FromSeconds(1));

        // Second signal/wait cycle
        this._waiter.SignalInput();
        await this._waiter.WaitForInputAsync(TimeSpan.FromSeconds(1));
    }

    [Fact]
    public async Task InputWaiter_WaitForInputAsync_CompletesWhenTimeoutExpiresAsync()
    {
        // Verify that a finite timeout releases the block even without a signal.
        // We only assert that it *does* complete (within a generous outer bound);
        // we intentionally do not assert that it stays blocked until the timeout,
        // because that would re-introduce the same wall-clock flakiness
        // described in BlocksUntilSignaledAsync (see comment on that test).
        Task waitTask = this._waiter.WaitForInputAsync(TimeSpan.FromMilliseconds(300));

        Task completed = await Task.WhenAny(waitTask, Task.Delay(TimeSpan.FromSeconds(5)));
        completed.Should().BeSameAs(waitTask, "the wait task should complete once the timeout expires");
        await waitTask;
    }
}

public class OutputFilterTests
{
    private static OutputFilter CreateFilterWithOutputFrom(string outputExecutorId)
    {
        NoOpExecutor start = new("start");
        NoOpExecutor end = new("end");

        Workflow workflow = new WorkflowBuilder("start")
            .AddEdge(start, end)
            .WithOutputFrom(outputExecutorId == "end" ? end : start)
            .Build();

        return new OutputFilter(workflow);
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsTrueForRegisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("end", "some output").Should().BeTrue("the executor was registered via WithOutputFrom");
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForUnregisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("start", "some output").Should().BeFalse("start was not registered as an output executor");
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForNonExistentExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("nonexistent", "some output").Should().BeFalse("an executor not in the workflow should not be an output executor");
    }

    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }
}
