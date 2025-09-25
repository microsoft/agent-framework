// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Reflection;

internal static class ValueTaskReflection
{
    private const string Nameof_AsTask = nameof(ValueTask<object>.AsTask);
    internal static readonly MethodInfo AsTask = typeof(ValueTask<>).GetMethod(Nameof_AsTask, BindingFlags.Public | BindingFlags.Instance)!;

    internal static MethodInfo ReflectAsTask(this Type specializedType)
    {
        Debug.Assert(specializedType.IsGenericType &&
                     specializedType.GetGenericTypeDefinition() == typeof(ValueTask<>), "specializedType must be a ValueTask<> type.");

        return specializedType.GetMethodFromGenericMethodDefinition(AsTask);
    }

    internal static bool IsValueTaskType(this Type type) => type.IsGenericType && type.GetGenericTypeDefinition() == typeof(ValueTask<>);
}

internal static class TaskReflection
{
    private const string Nameof_Result = nameof(Task<object>.Result);
    internal static readonly MethodInfo Result_get = typeof(Task<>).GetProperty(Nameof_Result)!.GetMethod!;

    internal static MethodInfo ReflectResult_get(this Type specializedType)
    {
        Debug.Assert(specializedType.IsGenericType &&
                     specializedType.GetGenericTypeDefinition() == typeof(Task<>), "specializedType must be a ValueTask<> type.");

        return specializedType.GetMethodFromGenericMethodDefinition(Result_get);
    }

    internal static bool IsTaskType(this Type type) => type.IsGenericType && type.GetGenericTypeDefinition() == typeof(Task<>);
}

internal static class ValueTaskTypeErasure
{
    internal static Func<object, ValueTask<object?>> UnwrapperFor(Type expectedResultType)
    {
        return UnwrapAndEraseAsync;

        async ValueTask<object?> UnwrapAndEraseAsync(object maybeGenericVT)
        {
            // This method handles only ValueTask<TResult> types.
            Type maybeVTType = maybeGenericVT.GetType();

            if (!maybeVTType.IsValueTaskType())
            {
                throw new InvalidOperationException($"Expected ValueTask or ValueTask<{expectedResultType.Name}>, but got {maybeGenericVT.GetType().Name}.");
            }

            MethodInfo asTaskMethod = maybeVTType.ReflectAsTask();
            Debug.Assert(asTaskMethod.ReturnType.IsTaskType(), "AsTask must return a Task<> type.");

            MethodInfo getResultMethod = asTaskMethod.ReturnType.ReflectResult_get();
            Type actualResultType = getResultMethod.ReturnType;

            if (!expectedResultType.IsAssignableFrom(actualResultType))
            {
                throw new InvalidOperationException($"Expected ValueTask<{expectedResultType.Name}> or a compatible type, but got ValueTask<{actualResultType.Name}>.");
            }

            Task task = (Task)asTaskMethod.ReflectionInvoke(maybeGenericVT)!;
            await task.ConfigureAwait(false); // TODO: Could we need to capture the context here?
            return getResultMethod.ReflectionInvoke(task);
        }
    }
}
