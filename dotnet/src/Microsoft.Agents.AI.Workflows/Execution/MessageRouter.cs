// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
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
    private readonly Type[] _interfaceHandlers;
    //private readonly Dictionary<Type, MessageHandlerF> _typedHandlers;
    //private readonly Dictionary<TypeId, Type> _runtimeTypeMap = new();

    private readonly ConcurrentDictionary<TypeId, TypeHandlingInfo> _typeInfos = new();

    private record TypeHandlingInfo(Type RuntimeType, MessageHandlerF Handler)
    {
        [Conditional("DEBUG")]
        private void AssertTypeCovaraince(Type expectedDerviedType) => Debug.Assert(this.RuntimeType.IsAssignableFrom(expectedDerviedType));

        public TypeHandlingInfo ForDerviedType(Type derivedType)
        {
            this.AssertTypeCovaraince(derivedType);

            return this with { RuntimeType = derivedType };
        }
    }

    private readonly CatchAllF? _catchAllFunc;

    internal MessageRouter(Dictionary<Type, MessageHandlerF> handlers, HashSet<Type> outputTypes, CatchAllF? catchAllFunc)
    {
        Throw.IfNull(handlers);

        HashSet<Type> interfaceHandlers = new();
        foreach (Type type in handlers.Keys)
        {
            this._typeInfos[new(type)] = new(type, handlers[type]);

            if (type.IsInterface)
            {
                interfaceHandlers.Add(type);
            }
        }

        this._interfaceHandlers = interfaceHandlers.ToArray();
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
            TypeId candidateTypeId = new(candidateType);
            if (this._typeInfos.TryGetValue(candidateTypeId, out TypeHandlingInfo? handlingInfo))
            {
                if (candidateType != messageType)
                {
                    TypeHandlingInfo actualInfo = handlingInfo.ForDerviedType(messageType);
                    this._typeInfos.TryAdd(new(messageType), actualInfo);
                }

                return handlingInfo.Handler;
            }
            else if (this._interfaceHandlers.Length > 0)
            {
                foreach (Type interfaceType in this._interfaceHandlers.Where(it => it.IsAssignableFrom(candidateType)))
                {
                    handlingInfo = this._typeInfos[new(interfaceType)];

                    // By definition we do not have a pre-calculated handler information for this candidateType, otherwise
                    // we would have found it above. This also means we do not have a corresponding entry for the messageType.
                    this._typeInfos.TryAdd(new(messageType), handlingInfo.ForDerviedType(messageType));

                    return handlingInfo.Handler;
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
            this._typeInfos.TryGetValue(portableValue.TypeId, out TypeHandlingInfo? handlingInfo))
        {
            // If we found a runtime type, we can use it
            message = portableValue.AsType(handlingInfo.RuntimeType) ?? message;
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
