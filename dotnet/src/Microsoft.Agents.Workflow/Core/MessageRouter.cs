// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

using HandlerInfosT =
    System.Collections.Generic.Dictionary<
        System.Type,
        Microsoft.Agents.Workflows.Core.MessageHandlerInfo
    >;

namespace Microsoft.Agents.Workflows.Core;

internal class MessageRouter
{
    // TODO: The goal of the cache is to allow SourceGenerators to do the reflection to bind the handlers in the router.
    internal static readonly Dictionary<Type, Func<MessageRouter>> s_routerFactoryCache = new();

    private Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> BoundHandlers { get; init; } = new();
    private IDefaultMessageHandler? DefaultHandler { get; init; } = null;

    [SuppressMessage("Trimming",
        "IL2075:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The return value " +
        "of the source method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    [SuppressMessage("Trimming",
        "IL2070:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The parameter of " +
        "method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    private static HandlerInfosT ReflectHandlers(Type executorType)
    {
        // This method reflects over the methods of the executor type to find message handlers.
        HandlerInfosT handlers = new();

        // Get all implementations of IMessageHandler<TMessage> or IMessageHandler<TMessage, TResult>
        // and create a MessageHandlerInfo for each.
        if (!typeof(Executor).IsAssignableFrom(executorType))
        {
            throw new ArgumentException($"Type {executorType.FullName} is not a valid Executor type.", nameof(executorType));
        }

        if (executorType.IsAbstract || executorType.IsInterface)
        {
            throw new ArgumentException($"Type {executorType.FullName} cannot be abstract or an interface.", nameof(executorType));
        }

        // Iterate all interfaces implemented by the executor type.
        foreach (Type interfaceType in executorType.GetInterfaces())
        {
            // Check if the interface is a message handler.
            if (!interfaceType.IsGenericType)
            {
                continue;
            }

            if (interfaceType.IsGenericType && (interfaceType.GetGenericTypeDefinition() == typeof(IMessageHandler<>) ||
                                                interfaceType.GetGenericTypeDefinition() == typeof(IMessageHandler<,>)))
            {
                // Get the generic arguments of the interface.
                Type[] genericArguments = interfaceType.GetGenericArguments();
                if (genericArguments.Length < 1 || genericArguments.Length > 2)
                {
                    continue; // Invalid handler signature.
                }
                Type inType = genericArguments[0];
                Type? outType = genericArguments.Length == 2 ? genericArguments[1] : null;
                MethodInfo? method = interfaceType.GetMethod("HandleAsync");
                if (method != null)
                {
                    MessageHandlerInfo info = new(method) { InType = inType, OutType = outType };
                    handlers[inType] = info;
                }
            }
        }

        return handlers;
    }

    [SuppressMessage("Trimming",
        "IL2075:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The return value " +
        "of the source method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    internal static HandlerInfosT ReflectHandlers<TExecutor>() where TExecutor : Executor
        => ReflectHandlers(typeof(TExecutor));

    internal static MessageRouter BindMessageHandlers(Executor executor, bool checkType)
    {
        if (s_routerFactoryCache.TryGetValue(executor.GetType(), out var factory))
        {
            return factory();
        }

        // If no factory is found, reflect over the handlers
        HandlerInfosT handlers = ReflectHandlers(executor.GetType());

        Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> boundHandlers = new();
        foreach (Type inType in handlers.Keys)
        {
            MessageHandlerInfo handlerInfo = handlers[inType];
            Func<object, IWorkflowContext, ValueTask<CallResult>> boundHandler = handlerInfo.Bind(executor, checkType);
            boundHandlers.Add(inType, boundHandler); // TODO: Turn the error here into something more actionable.
        }

        return new MessageRouter(boundHandlers, executor as IDefaultMessageHandler);
    }

    internal MessageRouter(Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> handlers, IDefaultMessageHandler? defaultHandler = null)
    {
        this.BoundHandlers = handlers;
        this.DefaultHandler = defaultHandler;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="message"></param>
    /// <param name="context"></param>
    /// <param name="requireRoute"></param>
    /// <returns></returns>
    /// <exception cref="ArgumentNullException"></exception>
    /// <exception cref="NotImplementedException"></exception>
    public async ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false)
    {
        Throw.IfNull(message);

        // TODO: Implement base type delegation?
        CallResult? result = null;
        if (this.BoundHandlers.TryGetValue(message.GetType(), out Func<object, IWorkflowContext, ValueTask<CallResult>>? handler))
        {
            result = await handler(message, context).ConfigureAwait(false);
        }
        else if (this.DefaultHandler != null)
        {
            try
            {
                await this.DefaultHandler.HandleAsync(message, context).ConfigureAwait(false);
                result = CallResult.ReturnVoid();
            }
            catch (Exception e)
            {
                result = CallResult.RaisedException(wasVoid: true, e);
            }
        }

        return result;
    }

    public bool CanHandle(object message) => this.CanHandle(Throw.IfNull(message).GetType());

    public bool CanHandle(Type candidateType)
    {
        Throw.IfNull(candidateType);

        // Check if the router can handle the candidate type.
        return this.DefaultHandler != null || this.BoundHandlers.ContainsKey(candidateType);
    }

    public HashSet<Type> IncomingTypes
        => this.DefaultHandler != null
            ? [.. this.BoundHandlers.Keys, typeof(object)]
            : [.. this.BoundHandlers.Keys];
}
