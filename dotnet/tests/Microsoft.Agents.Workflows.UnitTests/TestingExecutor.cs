// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.UnitTests;

internal abstract class TestingExecutor<TIn, TOut> : Executor, IDisposable
{
    private readonly bool _loop;
    private readonly Func<TIn, IWorkflowContext, CancellationToken, ValueTask<TOut>>[] _actions;
    private readonly HashSet<CancellationToken> _linkedTokens = [];
    private CancellationTokenSource _internalCts = new();

    protected TestingExecutor(string? id = null, bool loop = false, params Func<TIn, IWorkflowContext, CancellationToken, ValueTask<TOut>>[] actions) : base(id)
    {
        this._loop = loop;
        this._actions = actions;
    }

    public void UnlinkCancellation(CancellationToken token) =>
        this._linkedTokens.Remove(token);

    public void LinkCancellation(CancellationToken token)
    {
        this._linkedTokens.Add(token);
        CancellationTokenSource tokenSource = CancellationTokenSource.CreateLinkedTokenSource(this._linkedTokens.ToArray());
        tokenSource = Interlocked.Exchange(ref this._internalCts, tokenSource);
        tokenSource.Dispose();
    }

    public void SetCancel() =>
        Volatile.Read(ref this._internalCts).Cancel();

    protected sealed override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TIn, TOut>(this.RouteToActionsAsync);

    private int _nextActionIndex;
    private ValueTask<TOut> RouteToActionsAsync(TIn message, IWorkflowContext context)
    {
        if (this._nextActionIndex >= this._actions.Length)
        {
            if (this._loop)
            {
                this._nextActionIndex = 0;
            }
            else
            {
                throw new InvalidOperationException("No more actions to execute and looping is disabled.");
            }
        }

        try
        {
            Func<TIn, IWorkflowContext, CancellationToken, ValueTask<TOut>> action = this._actions[this._nextActionIndex];
            return action(message, context, Volatile.Read(ref this._internalCts).Token);
        }
        finally
        {
            this._nextActionIndex++;
        }
    }

    ~TestingExecutor()
    {
        this.Dispose(false);
    }

    protected virtual void Dispose(bool disposing) =>
        this._internalCts.Dispose();

    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }
}
