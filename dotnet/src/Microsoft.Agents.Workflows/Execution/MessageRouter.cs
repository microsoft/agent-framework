// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

using MessageHandlerF =
    System.Func<
        object, // message
        Microsoft.Agents.Workflows.IWorkflowContext, // context
        System.Threading.Tasks.ValueTask<Microsoft.Agents.Workflows.Execution.CallResult>
    >;

namespace Microsoft.Agents.Workflows.Execution;

internal class MessageRouter
{
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers;
    private readonly ConcurrentDictionary<Type, MessageHandlerF?> _dynamicTypedHandlers = [];
    private readonly bool _hasCatchall;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers)
    {
        this._typedHandlers = Throw.IfNull(handlers);
        this._hasCatchall = this._typedHandlers.ContainsKey(typeof(object));

        this.IncomingTypes = [.. this._typedHandlers.Keys];
    }

    public HashSet<Type> IncomingTypes { get; }

    public bool CanHandle(object message) => this.CanHandle(Throw.IfNull(message).GetType());

    public bool CanHandle(Type candidateType) =>
        this._hasCatchall ||
        this._typedHandlers.ContainsKey(candidateType) ||
        (this.GetDynamicTypedHandler(candidateType) is not null);

    public async ValueTask<CallResult?> RouteMessageAsync(object message, Type messageType, IWorkflowContext context, bool requireRoute = false)
    {
        Throw.IfNull(message);

        CallResult? result = null;

        try
        {
            if (this._typedHandlers.TryGetValue(messageType, out MessageHandlerF? handler) ||
                (handler = this.GetDynamicTypedHandler(messageType)) is not null)
            {
                result = await handler(message, context).ConfigureAwait(false);
            }
        }
        catch (Exception e)
        {
            result = CallResult.RaisedException(wasVoid: true, e);
        }

        return result;
    }

    private MessageHandlerF? GetDynamicTypedHandler(Type candidateType)
    {
        if (!this._dynamicTypedHandlers.TryGetValue(candidateType, out var handler))
        {
            // O(N) search through the registered types to see if any are assignable from the candidate type.
            foreach (var entry in this._typedHandlers)
            {
                if (entry.Key.IsAssignableFrom(candidateType))
                {
                    handler = entry.Value;
                    break;
                }
            }

            // The result, either the found handler or null, is cached in _dynamicTypedHandlers to avoid repeated
            // searches for the same type. As long as the number of types in the system is fixed,
            // GetDynamicTypedHandler becomes amortized O(1). Concurrent usage is safe; if two threads
            // invoke GetDynamicTypedHandler, the worst that happens is they duplicate each other's idempotent work.
            this._dynamicTypedHandlers[candidateType] = handler;
        }

        return handler;
    }
}
