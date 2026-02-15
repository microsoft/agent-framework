// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using System.Threading.Tasks.Sources;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class TestValueTaskSource<T> : IValueTaskSource<T>
{
    private int _status = (int)ValueTaskSourceStatus.Pending;
    private T? _value;
    private Exception? _exception;
    private int _continuationScheduled;
    private readonly object _continuationMutex = new();

    private bool _ranContinuation;
    private Action _continuationClosure = () => { };

    public TestValueTaskSource()
    {
    }

    private bool TrySetCompletionStatus(ValueTaskSourceStatus status)
        => Interlocked.CompareExchange(ref this._status,
                                       value: (int)status,
                                       comparand: (int)ValueTaskSourceStatus.Pending)
                                               == (int)ValueTaskSourceStatus.Pending;

    private void RunScheduledContinuation()
    {
        Console.WriteLine("Running scheduled continuation");
        lock (this._continuationMutex)
        {
            this._ranContinuation = true;
            this._continuationClosure();
        }
    }

    public ValueTask SetSucceededAsync(T value)
    {
        Console.WriteLine($"Setting succeeded {value}");

        if (this.TrySetCompletionStatus(ValueTaskSourceStatus.Succeeded))
        {
            // If the status was Pending, we can set it
            this._value = value;
        }

        this.RunScheduledContinuation();
        return new();
    }

    public ValueTask SetFaultedAsync(Exception exception)
    {
        Console.WriteLine($"Setting faulted {exception}");

        if (this.TrySetCompletionStatus(ValueTaskSourceStatus.Faulted))
        {
            // If the status was Pending, we can set it
            this._exception = exception;
        }

        this.RunScheduledContinuation();
        return new();
    }

    public ValueTask SetCanceledAsync()
    {
        Console.WriteLine("Setting canceled");

        this.TrySetCompletionStatus(ValueTaskSourceStatus.Canceled);
        this.RunScheduledContinuation();
        return new();
    }

    public T GetResult(short token)
    {
        Debug.Assert(token == 0);

        switch (this.GetStatus(0))
        {
            case ValueTaskSourceStatus.Succeeded:
                return this._value!;
            case ValueTaskSourceStatus.Faulted:
                throw this._exception!;
            case ValueTaskSourceStatus.Canceled:
                throw new TaskCanceledException();
            case ValueTaskSourceStatus.Pending:
                throw new InvalidOperationException("The operation is not yet completed.");
            default:
                throw new NotSupportedException();
        }
    }

    public ValueTaskSourceStatus GetStatus(short token)
    {
        Debug.Assert(token == 0);

        return (ValueTaskSourceStatus)Volatile.Read(ref this._status);
    }

    public void OnCompleted(Action<object?> continuation, object? state, short token, ValueTaskSourceOnCompletedFlags flags)
    {
        Debug.Assert(token == 0);

        if (Interlocked.Exchange(ref this._continuationScheduled, 1) == 1)
        {
            throw new InvalidOperationException("Cannot schedule more than one continuation on ValueTaskSource");
        }

        lock (this._continuationMutex)
        {
            if (this._ranContinuation)
            {
                // The default no-op was run, since we have not yet scheduled a continuation
                // Run this continuation immediately
                Console.WriteLine("Running continuation");
                continuation(state);
            }
            else
            {
                Console.WriteLine("Scheduling continuation");
                this._continuationClosure = () => continuation(state);
            }
        }
    }
}
