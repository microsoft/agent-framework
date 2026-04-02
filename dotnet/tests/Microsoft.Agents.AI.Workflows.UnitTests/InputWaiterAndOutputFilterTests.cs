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
        Task waitTask = this._waiter.WaitForInputAsync(TimeSpan.FromSeconds(5));

        await Task.Delay(50);
        waitTask.IsCompleted.Should().BeFalse("the waiter should block until input is signaled");

        this._waiter.SignalInput();

        Task completed = await Task.WhenAny(waitTask, Task.Delay(TimeSpan.FromSeconds(1)));
        completed.Should().BeSameAs(waitTask, "the wait task should complete after being signaled");
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
