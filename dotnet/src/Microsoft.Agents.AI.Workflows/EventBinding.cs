// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal class EventBinding<TEvent> where TEvent : WorkflowEvent
{
    private readonly EventChain<TEvent> _eventChain;

    internal EventBinding(EventChain<TEvent> eventChain)
    {
        this._eventChain = eventChain;
    }

    internal ValueTask<bool> RaiseAsync(TEvent evt, CancellationToken cancelationToken)
        => this._eventChain.RaiseAsync(evt, cancelationToken);

    public event WorkflowEventHandler<TEvent>? Event
    {
        add => this._eventChain.AttachHandler(value);
        remove => this._eventChain.DetachHandler(value);
    }

    public event WorkflowEventHandlerAsync<TEvent>? AsyncEvent
    {
        add => this._eventChain.AttachHandler(value);
        remove => this._eventChain.DetachHandler(value);
    }
}
