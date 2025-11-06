// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal class EventChain<TEvent> : IWorkflowEventChain, IDisposable where TEvent : WorkflowEvent
{
    private readonly SemaphoreSlim _semaphore = new(1, 1);
    private readonly List<Func<TEvent, ValueTask<bool>>> _handlers = new();
    private readonly Dictionary<object, Func<TEvent, ValueTask<bool>>> _handlerMap = new();

    ValueTask<bool> IWorkflowEventChain.RaiseAsync(WorkflowEvent evt, CancellationToken cancellationToken)
    {
        if (evt is TEvent typedEvent)
        {
            return this.RaiseAsync(typedEvent, cancellationToken);
        }

        throw new InvalidOperationException($"Sending event of type {evt.GetType().FullName} to event chain for " +
            $"type {typeof(TEvent).FullName}.");
    }

    public async ValueTask<bool> RaiseAsync(TEvent evt, CancellationToken cancellationToken)
    {
        await this._semaphore.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            foreach (Func<TEvent, ValueTask<bool>> handler in this._handlers)
            {
                bool handled = await handler(evt).ConfigureAwait(false);
                if (handled)
                {
                    return true;
                }
            }

            return false;
        }
        finally
        {
            this._semaphore.Release();
        }
    }

    private bool AttachHandler(Func<TEvent, ValueTask<bool>> handlerAsync, object key)
    {
        this._semaphore.Wait();

        bool shouldAdd = !this._handlerMap.ContainsKey(key);
        if (shouldAdd)
        {
            this._handlerMap.Add(key, handlerAsync);
            this._handlers.Add(handlerAsync);
        }

        this._semaphore.Release();
        return shouldAdd;
    }

    private bool DetachHandler(object key)
    {
        this._semaphore.Wait();

        bool removed = false;
        if (this._handlerMap.TryGetValue(key, out Func<TEvent, ValueTask<bool>>? handler))
        {
            this._handlers.Remove(handler);
            removed = true;
        }

        this._semaphore.Release();
        return removed;
    }

    public bool AttachHandler(WorkflowEventHandlerAsync<TEvent>? handlerAsync)
        => handlerAsync is not null
         ? this.AttachHandler(handlerAsync.Invoke, handlerAsync)
         : false;

    public bool AttachHandler(WorkflowEventHandler<TEvent>? handler)
        => handler is not null
         ? this.AttachHandler(evt => new(handler.Invoke(evt)), handler)
         : false;

    public bool DetachHandler(WorkflowEventHandlerAsync<TEvent>? handlerAsync)
        => handlerAsync is not null
         ? this.DetachHandler((object)handlerAsync)
         : false;

    public bool DetachHandler(WorkflowEventHandler<TEvent>? handler)
        => handler is not null
         ? this.DetachHandler((object)handler)
         : false;

    public void Dispose()
    {
        this._semaphore.Dispose();
    }
}
