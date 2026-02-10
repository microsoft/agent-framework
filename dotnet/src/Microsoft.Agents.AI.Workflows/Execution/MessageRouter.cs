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
    private readonly HashSet<Type> _interfaceHandlers = new();
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers;
    private readonly Dictionary<TypeId, Type> _runtimeTypeMap = new();

    private readonly CatchAllF? _catchAllFunc;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers, HashSet<Type> outputTypes, CatchAllF? catchAllFunc)
    {
        Throw.IfNull(handlers);

        this._typedHandlers = handlers;

        foreach (Type type in handlers.Keys)
        {
            this._runtimeTypeMap[new(type)] = type;

            if (type.IsInterface)
            {
                this._interfaceHandlers.Add(type);
            }
        }

        this._catchAllFunc = catchAllFunc;

        this.IncomingTypes = [.. handlers.Keys];
        this.DefaultOutputTypes = outputTypes;
    }

    public HashSet<Type> IncomingTypes { get; }

    [MemberNotNullWhen(true, nameof(_catchAllFunc))]
    internal bool HasCatchAll => this._catchAllFunc is not null;

    public bool CanHandle(object message) => this.CanHandle(Throw.IfNull(message).GetType());
    public bool CanHandle(Type candidateType) => this.HasCatchAll || this.FindHandler(candidateType) is not null;

    public HashSet<Type> DefaultOutputTypes { get; }

    private MessageHandlerF? FindHandler(Type messageType)
    {
        for (Type? candidateType = messageType; candidateType != null; candidateType = candidateType.BaseType)
        {
            if (this._typedHandlers.TryGetValue(candidateType, out MessageHandlerF? handler))
            {
                if (candidateType != messageType)
                {
                    // Cache the handler for future lookups.
                    this._typedHandlers[messageType] = handler;
                    this._runtimeTypeMap[new TypeId(messageType)] = candidateType;
                }

                return handler;
            }
            else if (this._interfaceHandlers.Count > 0)
            {
                foreach (Type interfaceType in this._interfaceHandlers.Where(it => it.IsAssignableFrom(candidateType)))
                {
                    handler = this._typedHandlers[interfaceType];
                    this._typedHandlers[messageType] = handler;

                    // TODO: This could cause some consternation with Checkpointing (need to ensure we surface errors well)
                    this._runtimeTypeMap[new TypeId(messageType)] = interfaceType;
                    return handler;
                }
            }
        }

        return null;
    }

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
            MessageHandlerF? handler = this.FindHandler(message.GetType());
            if (handler != null)
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
