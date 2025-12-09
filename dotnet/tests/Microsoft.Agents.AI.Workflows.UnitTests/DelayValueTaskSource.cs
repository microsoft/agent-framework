// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using System.Threading.Tasks.Sources;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class DelayValueTaskSource<T> : IValueTaskSource<T>
{
    private readonly TestValueTaskSource<T> _innerSource = new();
    private readonly T _value;

    public DelayValueTaskSource(T value)
    {
        this._value = value;
    }

    public ValueTask ReleaseSucceededAsync() => this._innerSource.SetSucceededAsync(this._value);
    public ValueTask ReleaseFaultedAsync(Exception exception) => this._innerSource.SetFaultedAsync(exception);
    public ValueTask ReleaseCanceledAsync() => this._innerSource.SetCanceledAsync();

    public T GetResult(short token) => this._innerSource.GetResult(token);

    public ValueTaskSourceStatus GetStatus(short token) => this._innerSource.GetStatus(token);

    public void OnCompleted(Action<object?> continuation, object? state, short token, ValueTaskSourceOnCompletedFlags flags)
        => this._innerSource.OnCompleted(continuation, state, token, flags);
}
