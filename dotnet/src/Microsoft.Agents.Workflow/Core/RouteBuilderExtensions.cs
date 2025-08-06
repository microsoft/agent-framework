// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

internal static class RouteBuilderExtensions
{
    [SuppressMessage("Trimming",
    "IL2075:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The return value " +
    "of the source method does not have matching annotations.",
    Justification = "Trimming attributes are inaccessible in 472")]
    [SuppressMessage("Trimming",
    "IL2070:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The parameter of " +
    "method does not have matching annotations.",
    Justification = "Trimming attributes are inaccessible in 472")]
    private static IEnumerable<MessageHandlerInfo> GetHandlerInfos(this Type executorType)
    {
        // Handlers are defined by implementations of IMessageHandler<TMessage> or IMessageHandler<TMessage, TResult>
        Debug.Assert(typeof(Executor).IsAssignableFrom(executorType), "executorType must be an Executor type.");

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
                    yield return new MessageHandlerInfo(method) { InType = inType, OutType = outType };
                }
            }
        }
    }

    public static RouteBuilder ReflectHandlers(this RouteBuilder builder, Type executorType, Executor executor)
    {
        Throw.IfNull(builder);
        Throw.IfNull(executorType);

        Debug.Assert(typeof(Executor).IsAssignableFrom(executorType), "executorType must be an Executor type.");

        foreach (MessageHandlerInfo handlerInfo in executorType.GetHandlerInfos())
        {
            builder = builder.AddHandler(handlerInfo.InType, handlerInfo.Bind(executor, checkType: true));
        }

        if (executor is IDefaultMessageHandler defaultHandler)
        {
            builder = builder.AddHandler<object>(defaultHandler.HandleAsync);
        }

        return builder;
    }

    public static RouteBuilder ReflectHandlers<TExecutor>(this RouteBuilder builder, TExecutor executor) where TExecutor : Executor
        => builder.ReflectHandlers(executor.GetType(), executor);
}
