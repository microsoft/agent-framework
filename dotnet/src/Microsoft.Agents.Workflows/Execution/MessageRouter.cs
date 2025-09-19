// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

using MessageHandlerF =
    System.Func<
        object, // message
        Microsoft.Agents.Workflows.IWorkflowContext, // context
        System.Threading.Tasks.ValueTask<Microsoft.Agents.Workflows.Execution.CallResult>
    >;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class MessageRouter
{
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers;
    private readonly Dictionary<TypeId, Type> _runtimeTypeMap;
    private readonly MessageHandlerF? _catchAllHandler;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers)
    {
        Throw.IfNull(handlers);

        this._typedHandlers = handlers;
        this._runtimeTypeMap = handlers.Keys.ToDictionary(t => new TypeId(t), t => t);
        this._catchAllHandler = handlers.FirstOrDefault(e => e.Key == typeof(object)).Value;

        this.IncomingTypes = [.. handlers.Keys];
    }

    public HashSet<Type> IncomingTypes { get; }

    public bool CanHandle(object message) => this.CanHandle(new TypeId(Throw.IfNull(message).GetType()));
    public bool CanHandle(Type candidateType) => this.CanHandle(new TypeId(Throw.IfNull(candidateType)));

    public bool CanHandle(TypeId candidateType)
    {
        return this._catchAllHandler is not null || this._runtimeTypeMap.ContainsKey(candidateType);
    }

    public async ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false)
    {
        Throw.IfNull(message);

        CallResult? result = null;

        if (message is PortableValue portableValue &&
            this._runtimeTypeMap.TryGetValue(portableValue.TypeId, out Type? runtimeType))
        {
            // If we found a runtime type, we can use it
            message = portableValue.AsType(runtimeType) ?? message;
        }

        try
        {
            if (this._typedHandlers.TryGetValue(message.GetType(), out MessageHandlerF? handler) ||
                (handler = this._catchAllHandler) is not null)
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
}
