// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public static class RunStatusTests
{
    internal sealed class TestStepRunner : ISuperStepRunner
    {
        public TestStepRunner([CallerMemberName] string? name = null)
        {
            Console.WriteLine($"Starting test {name}");
        }

        public string RunId { get; } = Guid.NewGuid().ToString("N");

        public string StartExecutorId { get; } = "start";

        public bool HasUnservicedRequests { get; set; }
        public bool HasUnprocessedMessages { get; set; }

        public ConcurrentEventSink OutgoingEvents { get; } = new();

        public ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellationToken = default)
        {
            this.HasUnprocessedMessages = true;
            return new(true);
        }

        ValueTask<bool> ISuperStepRunner.EnqueueMessageUntypedAsync(object message, Type declaredType, CancellationToken cancellationToken)
        {
            this.HasUnprocessedMessages = true;
            return new(true);
        }

        public async ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default)
        {
            this.HasUnservicedRequests = false;
            await this.EnqueueMessageAsync(response, cancellationToken);
        }

        public ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellationToken = default) => new(true);

        public ValueTask RequestEndRunAsync()
        {
            if (this._currentStepSource != null)
            {
                return this.CancelStepAsync();
            }

            return new();
        }

        private DelayValueTaskSource<bool>? _currentStepSource;
        private CancellationTokenRegistration? _registration;

        ValueTask<bool> ISuperStepRunner.RunSuperStepAsync(CancellationToken cancellationToken)
        {
            Debug.Assert(Interlocked.CompareExchange(ref this._currentStepSource,
                                                     value: new DelayValueTaskSource<bool>(this.HasUnprocessedMessages),
                                                     null) is null);

            this._registration = cancellationToken.Register(() => _ = this._currentStepSource == null
                                                                    ? Task.CompletedTask
                                                                    : this._currentStepSource.ReleaseCanceledAsync().AsTask());
            this.HasUnprocessedMessages = false;

            return new(this._currentStepSource, 0);
        }

        private DelayValueTaskSource<bool> TakeCurrentStepSource()
        {
            DelayValueTaskSource<bool>? currentStepSource = Interlocked.Exchange(ref this._currentStepSource, null);
            Debug.Assert(currentStepSource is not null);
            this._registration?.Dispose();
            this._registration = null;

            return currentStepSource;
        }

        public ValueTask CompleteStepAsync() => this.TakeCurrentStepSource().ReleaseSucceededAsync();

        public ValueTask CompleteStepWithPendingAsync()
        {
            this.HasUnservicedRequests = true;
            return this.CompleteStepAsync();
        }

        public ValueTask CancelStepAsync() => this.TakeCurrentStepSource().ReleaseCanceledAsync();

        public ValueTask FailStepAsync(Exception exception) => this.TakeCurrentStepSource().ReleaseFaultedAsync(exception);
    }

    public enum EventStreamKind
    {
        OffThread,
        Lockstep
    }

    private static IRunEventStream GetRunStreamForKind(EventStreamKind kind, ISuperStepRunner stepRunner)
    {
        IRunEventStream result;
        switch (kind)
        {
            case EventStreamKind.OffThread:
                result = new StreamingRunEventStream(stepRunner);
                break;
            case EventStreamKind.Lockstep:
                result = new LockstepRunEventStream(stepRunner);
                break;
            default:
                throw new NotSupportedException($"Unsupported RunStream kind: {kind}");
        }

        result.Start();
        return result;
    }

    [Theory]
    [InlineData(EventStreamKind.OffThread)]
    [InlineData(EventStreamKind.Lockstep)]
    public static async Task Test_RunStatus_NotStartedWhenStartingAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.NotStarted);
    }

    [Theory]
    [InlineData(EventStreamKind.OffThread)]
    [InlineData(EventStreamKind.Lockstep)]
    public static async Task Test_RunStatus_RunningWhenInSuperstepAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        await runner.EnqueueMessageAsync(new object());
        eventStream.SignalInput();

        _ = WatchStreamAsync();

        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Running);

        await eventStream.DisposeAsync();

        async Task WatchStreamAsync()
        {
            await foreach (var _ in eventStream.TakeEventStreamAsync(false)) { }
        }
    }

    [Theory]
    [InlineData(EventStreamKind.OffThread)]
    [InlineData(EventStreamKind.Lockstep)]
    public static async Task Test_RunStatus_IdleWhenFinishedSuperstepsAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        await runner.EnqueueMessageAsync(new object());
        eventStream.SignalInput();

        Task watchTask = WatchStreamAsync();
        await runner.CompleteStepAsync();
        await watchTask;

        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        await eventStream.DisposeAsync();

        async Task WatchStreamAsync()
        {
            await foreach (var _ in eventStream.TakeEventStreamAsync(false)) { }
        }
    }

    [Theory]
    [InlineData(EventStreamKind.OffThread)]
    [InlineData(EventStreamKind.Lockstep)]
    public static async Task Test_RunStatus_EndedWhenCancelledAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        await runner.EnqueueMessageAsync(new object());
        eventStream.SignalInput();

        Task watchTask = WatchStreamAsync();
        await runner.CancelStepAsync();
        await watchTask;

        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Ended);

        await eventStream.DisposeAsync();

        async Task WatchStreamAsync()
        {
            await foreach (var _ in eventStream.TakeEventStreamAsync(false)) { }
        }
    }

    [Theory]
    [InlineData(EventStreamKind.OffThread)]
    [InlineData(EventStreamKind.Lockstep)]
    public static async Task Test_RunStatus_ExceptionWhenFaultedAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        await runner.EnqueueMessageAsync(new object());
        eventStream.SignalInput();

        Task watchTask = WatchStreamAsync();
        await runner.FailStepAsync(new InvalidOperationException());
        await watchTask;

        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Ended);

        await eventStream.DisposeAsync();

        async Task WatchStreamAsync()
        {
            await foreach (var _ in eventStream.TakeEventStreamAsync(false)) { }
        }
    }

    //[Theory]
    //[InlineData(EventStreamKind.OffThread)]
    //[InlineData(EventStreamKind.Lockstep)]
    internal static async Task Test_RunStatus_PendingRequestsAsync(EventStreamKind mode)
    {
        TestStepRunner runner = new();
        IRunEventStream eventStream = GetRunStreamForKind(mode, runner);

        // Act 1: Send the input object, and run the step to PendingRequest
        await runner.EnqueueMessageAsync(new object());
        eventStream.SignalInput();

        Task watchTask = WatchStreamAsync();
        await runner.CompleteStepWithPendingAsync();
        await watchTask;

        // Assert 1
        RunStatus status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.PendingRequests);

        // Act 2: Send the response, check running state
        await runner.EnqueueResponseAsync(
            new ExternalResponse(
                new Checkpointing.RequestPortInfo(new(typeof(object)), new(typeof(object)), "_"),
                Guid.NewGuid().ToString("N"),
                new(new())));
        eventStream.SignalInput();

        watchTask = WatchStreamAsync();

        // Assert 2
        status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Running);

        // Act 3: Process the response, check state is idle
        await runner.CompleteStepAsync();
        await watchTask; status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Running);

        // Assert 3
        status = await eventStream.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        await eventStream.DisposeAsync();

        async Task WatchStreamAsync()
        {
            await foreach (var _ in eventStream.TakeEventStreamAsync(false)) { }
        }
    }
}
