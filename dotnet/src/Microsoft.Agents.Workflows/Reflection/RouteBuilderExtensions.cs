// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Reflection;

internal static class IMessageHandlerReflection
{
    private const string Nameof_HandleAsync = nameof(IMessageHandler<object>.HandleAsync);
    internal static readonly MethodInfo HandleAsync_1 = typeof(IMessageHandler<>).GetMethod(Nameof_HandleAsync, BindingFlags.Public | BindingFlags.Instance)!;
    internal static readonly MethodInfo HandleAsync_2 = typeof(IMessageHandler<,>).GetMethod(Nameof_HandleAsync, BindingFlags.Public | BindingFlags.Instance)!;

    internal static MethodInfo ReflectHandle(this Type specializedType, int genericArgumentCount)
    {
        Debug.Assert(specializedType.IsGenericType &&
                     (specializedType.GetGenericTypeDefinition() == typeof(IMessageHandler<>) ||
                      specializedType.GetGenericTypeDefinition() == typeof(IMessageHandler<,>)),
            "specializedType must be an IMessageHandler<> or IMessageHandler<,> type.");
        return genericArgumentCount switch
        {
            1 => specializedType.GetMethodFromGenericMethodDefinition(HandleAsync_1),
            2 => specializedType.GetMethodFromGenericMethodDefinition(HandleAsync_2),
            _ => throw new ArgumentOutOfRangeException(nameof(genericArgumentCount), "Must be 1 or 2.")
        };
    }

    internal static int GenericArgumentCount(this Type type)
    {
        Debug.Assert(type.IsMessageHandlerType(), "type must be an IMessageHandler<> or IMessageHandler<,> type.");
        return type.GetGenericArguments().Length;
    }

    internal static bool IsMessageHandlerType(this Type type) =>
        type.IsGenericType &&
        (type.GetGenericTypeDefinition() == typeof(IMessageHandler<>) ||
         type.GetGenericTypeDefinition() == typeof(IMessageHandler<,>));
}

internal static class RouteBuilderExtensions
{
    private static IEnumerable<MessageHandlerInfo> GetHandlerInfos(
        [DynamicallyAccessedMembers(ReflectionDemands.RuntimeInterfaceDiscoveryAndInvocation)]
        this Type executorType)
    {
        // Handlers are defined by implementations of IMessageHandler<TMessage> or IMessageHandler<TMessage, TResult>
        Debug.Assert(typeof(Executor).IsAssignableFrom(executorType), "executorType must be an Executor type.");

        foreach (Type interfaceType in executorType.GetInterfaces())
        {
            // Check if the interface is a message handler.
            if (!interfaceType.IsMessageHandlerType())
            {
                continue;
            }

            // Get the generic arguments of the interface.
            Type[] genericArguments = interfaceType.GetGenericArguments();
            if (genericArguments.Length is < 1 or > 2)
            {
                continue; // Invalid handler signature.
            }
            Type inType = genericArguments[0];
            Type? outType = genericArguments.Length == 2 ? genericArguments[1] : null;

            MethodInfo? method = interfaceType.ReflectHandle(genericArguments.Length);

            if (method is not null)
            {
                yield return new MessageHandlerInfo(method) { InType = inType, OutType = outType };
            }
        }
    }

    public static RouteBuilder ReflectHandlers<
        [DynamicallyAccessedMembers(
            ReflectionDemands.RuntimeInterfaceDiscoveryAndInvocation)
        ] TExecutor>
        (this RouteBuilder builder, ReflectingExecutor<TExecutor> executor)
        where TExecutor : ReflectingExecutor<TExecutor>
    {
        Throw.IfNull(builder);

        Type executorType = typeof(TExecutor);
        Debug.Assert(executorType.IsAssignableFrom(executor.GetType()),
            "executorType must be the same type or a base type of the executor instance.");

        foreach (MessageHandlerInfo handlerInfo in executorType.GetHandlerInfos())
        {
            builder = builder.AddHandler(handlerInfo.InType, handlerInfo.Bind(executor, checkType: true));
        }

        return builder;
    }
}
