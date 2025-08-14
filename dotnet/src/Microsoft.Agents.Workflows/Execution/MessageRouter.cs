// Copyright (c) Microsoft. All rights reserved.

using System;
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
    private readonly bool _hasCatchall;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers)
    {
        this._typedHandlers = Throw.IfNull(handlers);
        this._hasCatchall = this._typedHandlers.ContainsKey(typeof(object));
    }

    public HashSet<Type> IncomingTypes => [.. this._typedHandlers.Keys];

    public bool CanHandle(object message) => this.CanHandle(Throw.IfNull(message).GetType());

    public bool CanHandle(Type candidateType)
    {
        // For now we only support routing to handlers registered on the exact type (no base type delegation).
        return this._hasCatchall || this._typedHandlers.ContainsKey(candidateType);
    }

    public async ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false)
    {
        Throw.IfNull(message);

        CallResult? result = null;

        try
        {
            if (this._typedHandlers.TryGetValue(message.GetType(), out MessageHandlerF? handler))
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
