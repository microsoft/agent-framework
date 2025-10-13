// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;
using CatchAllF =
    System.Func<
        Microsoft.Agents.AI.Workflows.PortableValue, // message
        Microsoft.Agents.AI.Workflows.IWorkflowContext, // context
        System.Threading.CancellationToken, // cancellation
        System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Execution.CallResult>
    >;
using MessageHandlerF =
    System.Func<
        object, // message
        Microsoft.Agents.AI.Workflows.IWorkflowContext, // context
        System.Threading.CancellationToken, // cancellation
        System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Execution.CallResult>
    >;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class MessageRouter
{
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers;
    private readonly Dictionary<TypeId, Type> _runtimeTypeMap;

    private readonly CatchAllF? _catchAllFunc;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers, HashSet<Type> outputTypes, CatchAllF? catchAllFunc)
    {
        Throw.IfNull(handlers);

        this._typedHandlers = handlers;
        this._runtimeTypeMap = handlers.Keys.ToDictionary(t => new TypeId(t), t => t);
        this._catchAllFunc = catchAllFunc;

        this.IncomingTypes = [.. handlers.Keys];
        this.DefaultOutputTypes = outputTypes;
    }

    public HashSet<Type> IncomingTypes { get; }

    [MemberNotNullWhen(true, nameof(_catchAllFunc))]
    internal bool HasCatchAll => this._catchAllFunc is not null;

    public bool CanHandle(object message) => this.CanHandle(new TypeId(Throw.IfNull(message).GetType()));
    public bool CanHandle(Type candidateType) => this.CanHandle(new TypeId(Throw.IfNull(candidateType)));

    public bool CanHandle(TypeId candidateType)
    {
        return this.HasCatchAll || this._runtimeTypeMap.ContainsKey(candidateType);
    }

    public HashSet<Type> DefaultOutputTypes { get; }

    public async ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(message);

        CallResult? result = null;

        PortableValue? portableValue = message as PortableValue;
        if (portableValue != null &&
            this._runtimeTypeMap.TryGetValue(portableValue.TypeId, out Type? runtimeType))
        {
            // If we found a runtime type, we can use it
            message = portableValue.AsType(runtimeType) ?? message;
        }

        try
        {
            if (this._typedHandlers.TryGetValue(message.GetType(), out MessageHandlerF? handler))
            {
                result = await handler(message, context, cancellationToken).ConfigureAwait(false);
            }
            else if (this.HasCatchAll)
            {
                portableValue ??= new PortableValue(message);

                result = await this._catchAllFunc(portableValue, context, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (Exception e)
        {
            result = CallResult.RaisedException(wasVoid: true, e);
        }

        return result;
    }
}
