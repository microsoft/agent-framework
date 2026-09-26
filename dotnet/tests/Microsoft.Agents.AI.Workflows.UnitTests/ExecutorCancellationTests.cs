// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CS0618 // Verify cancellation in the supported legacy reflection path too.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class ExecutorCancellationTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SynchronousReflectionCancellationDoesNotEmitFailureAsync(bool returnsResult)
    {
        // Arrange
        using CancellationTokenSource source = new();
        ValueTask CancelAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            source.Cancel();
            throw new OperationCanceledException(cancellationToken);
        }

        ValueTask<string> CancelWithResultAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            source.Cancel();
            throw new OperationCanceledException(cancellationToken);
        }

        Executor executor = returnsResult
            ? new ReflectingResultHandler(CancelWithResultAsync)
            : new ReflectingHandler(CancelAsync);
        TestWorkflowContext context = new(executor.Id);

        // Act
        OperationCanceledException exception = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => executor.ExecuteCoreAsync("input", new(typeof(string)), context, source.Token).AsTask());

        // Assert
        Assert.Equal(source.Token, exception.CancellationToken);
        Assert.DoesNotContain(context.EmittedEvents, evt => evt is ExecutorFailedEvent or ExecutorCompletedEvent);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RuntimeCancellationDoesNotEmitFailureAsync(bool useReflection)
    {
        // Arrange
        using CancellationTokenSource source = new();
        async ValueTask CancelAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            source.Cancel();
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
        }

        Executor executor = useReflection
            ? new ReflectingHandler(CancelAsync)
            : new FunctionExecutor<string>("cancel", CancelAsync);
        TestWorkflowContext context = new(executor.Id);

        // Act
        OperationCanceledException exception = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => executor.ExecuteCoreAsync("input", new(typeof(string)), context, source.Token).AsTask());

        // Assert
        Assert.Equal(source.Token, exception.CancellationToken);
        Assert.DoesNotContain(context.EmittedEvents, evt => evt is ExecutorFailedEvent or ExecutorCompletedEvent);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OrdinaryFailureRemainsFailureWhenRuntimeIsCancelledAsync(bool useReflection)
    {
        // Arrange
        using CancellationTokenSource source = new();
        InvalidOperationException expected = new("handler failed");
        async ValueTask FailAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await Task.Yield();
            source.Cancel();
            throw expected;
        }

        Executor executor = useReflection
            ? new ReflectingHandler(FailAsync)
            : new FunctionExecutor<string>("fail", FailAsync);
        TestWorkflowContext context = new(executor.Id);

        // Act
        TargetInvocationException exception = await Assert.ThrowsAsync<TargetInvocationException>(
            () => executor.ExecuteCoreAsync("input", new(typeof(string)), context, source.Token).AsTask());

        // Assert
        Assert.Same(expected, exception.InnerException);
        Assert.Contains(context.EmittedEvents, evt => evt is ExecutorFailedEvent);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CancellationWithoutRuntimeCancellationRetainsFailureBehaviorAsync(bool useReflection)
    {
        // Arrange
        async ValueTask CancelAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await Task.Yield();
            throw new OperationCanceledException();
        }

        Executor executor = useReflection
            ? new ReflectingHandler(CancelAsync)
            : new FunctionExecutor<string>("cancel", CancelAsync);
        TestWorkflowContext context = new(executor.Id);

        // Act
        TargetInvocationException exception = await Assert.ThrowsAsync<TargetInvocationException>(
            () => executor.ExecuteCoreAsync("input", new(typeof(string)), context).AsTask());

        // Assert: preserve the existing distinction between the two routing paths.
        if (useReflection)
        {
            Assert.Null(exception.InnerException);
        }
        else
        {
            Assert.IsType<OperationCanceledException>(exception.InnerException);
        }

        Assert.Contains(context.EmittedEvents, evt => evt is ExecutorFailedEvent);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RuntimeCancellationDoesNotSurfaceAsWorkflowErrorAsync(bool offThread)
    {
        // Arrange
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(30));
        TaskCompletionSource<bool> started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        Task deadline = Task.Delay(Timeout.InfiniteTimeSpan, timeout.Token);
        FunctionExecutor<string> executor = new("cancel", async (message, context, cancellationToken) =>
        {
            started.SetResult(true);
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
        });
        Workflow workflow = new WorkflowBuilder(executor).Build();
        var environment = offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep;
        List<WorkflowEvent> events = [];

        // Act
        await using StreamingRun run = await environment.RunStreamingAsync(workflow, "input");
        async Task ReadEventsAsync()
        {
            try
            {
                await foreach (WorkflowEvent evt in run.WatchStreamAsync(timeout.Token))
                {
                    events.Add(evt);
                }
            }
            catch (OperationCanceledException) when (!timeout.IsCancellationRequested)
            {
                // The stream may terminate through cancellation rather than normal completion.
            }
        }

        Task reading = ReadEventsAsync();
        Assert.Same(started.Task, await Task.WhenAny(started.Task, deadline));
        await run.CancelRunAsync();
        Assert.Same(reading, await Task.WhenAny(reading, deadline));
        await reading;

        // Assert
        Assert.False(timeout.IsCancellationRequested);
        Assert.DoesNotContain(events, evt => evt is ExecutorFailedEvent or WorkflowErrorEvent);
        timeout.Cancel();
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ForeignCancellationRemainsFailureWhenRuntimeIsCancelledAsync(bool useReflection, bool useDefaultToken)
    {
        // Arrange
        using CancellationTokenSource runtime = new();
        using CancellationTokenSource foreign = new();
        foreign.Cancel();
        OperationCanceledException expected = new(useDefaultToken ? CancellationToken.None : foreign.Token);
        async ValueTask CancelAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await Task.Yield();
            runtime.Cancel();
            throw expected;
        }

        Executor executor = useReflection
            ? new ReflectingHandler(CancelAsync)
            : new FunctionExecutor<string>("foreign", CancelAsync);
        TestWorkflowContext context = new(executor.Id);

        // Act
        TargetInvocationException exception = await Assert.ThrowsAsync<TargetInvocationException>(
            () => executor.ExecuteCoreAsync("input", new(typeof(string)), context, runtime.Token).AsTask());

        // Assert: preserve each routing path's existing failure shape.
        if (useReflection)
        {
            Assert.Null(exception.InnerException);
        }
        else
        {
            Assert.Same(expected, exception.InnerException);
        }

        Assert.Contains(context.EmittedEvents, evt => evt is ExecutorFailedEvent);
    }
    private sealed class ReflectingResultHandler(Func<string, IWorkflowContext, CancellationToken, ValueTask<string>> handler)
        : ReflectingExecutor<ReflectingResultHandler>("reflecting-result"), IMessageHandler<string, string>
    {
        public ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => handler(message, context, cancellationToken);
    }

    private sealed class ReflectingHandler(Func<string, IWorkflowContext, CancellationToken, ValueTask> handler)
        : ReflectingExecutor<ReflectingHandler>("reflecting"), IMessageHandler<string>
    {
        public ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => handler(message, context, cancellationToken);
    }
}
