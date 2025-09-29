// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;

#if !NET
using System.Linq;
#endif

namespace Microsoft.Agents.AI.Workflows.Reflection;

internal static class ReflectionDemands
{
    internal const DynamicallyAccessedMemberTypes ReflectedMethods = DynamicallyAccessedMemberTypes.PublicMethods | DynamicallyAccessedMemberTypes.NonPublicMethods;
    internal const DynamicallyAccessedMemberTypes ReflectedInterfaces = DynamicallyAccessedMemberTypes.Interfaces;

    internal const DynamicallyAccessedMemberTypes RuntimeInterfaceDiscoveryAndInvocation = ReflectedMethods | ReflectedInterfaces;
}

internal static class ReflectionExtensions
{
    public static object? ReflectionInvoke(this MethodInfo method, object? target, params object?[] arguments)
    {
#if NET
        return method.Invoke(target, BindingFlags.DoNotWrapExceptions, binder: null, arguments, culture: null);
#else
        try
        {
            return method.Invoke(target, BindingFlags.Default, binder: null, arguments, culture: null);
        }
        catch (TargetInvocationException e) when (e.InnerException is not null)
        {
            // If we're targeting .NET Framework, such that BindingFlags.DoNotWrapExceptions
            // is ignored, the original exception will be wrapped in a TargetInvocationException.
            // Unwrap it and throw that original exception, maintaining its stack information.
            System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(e.InnerException).Throw();
            throw;
        }
#endif
    }

    public static MethodInfo GetMethodFromGenericMethodDefinition(this Type specializedType, MethodInfo genericMethodDefinition)
    {
        Debug.Assert(specializedType.IsGenericType && specializedType.GetGenericTypeDefinition() == genericMethodDefinition.DeclaringType, "generic member definition doesn't match type.");
#if NET
        return (MethodInfo)specializedType.GetMemberWithSameMetadataDefinitionAs(genericMethodDefinition);
#else
        const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
        return specializedType.GetMethods(All).First(m => m.MetadataToken == genericMethodDefinition.MetadataToken);
#endif
    }
}
