// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

internal static class ValueTaskTypeErasure
{
    internal static Func<object, ValueTask<object?>> CreateErasingUnwrapper<TResult>()
    {
        return UnwrapAndEraseAsync;

        static async ValueTask<object?> UnwrapAndEraseAsync(object maybeValueTask)
        {
            if (maybeValueTask is ValueTask<TResult> vt)
            {
                // If the input is a ValueTask<TResult>, unwrap it.
                TResult result = await vt.ConfigureAwait(false);
                return (object?)result;
            }

            throw new InvalidOperationException($"Expected ValueTask or ValueTask<{typeof(TResult).Name}>, but got {maybeValueTask.GetType().Name}.");
        }
    }

#if NET5_0_OR_GREATER
    // This suppression is qualified because for some reason VS is not recognizing the attribute's presence, treating the
    // import as an error (due to unnecessary using).
    [System.Diagnostics.CodeAnalysis.RequiresDynamicCode("Calls System.Reflection.MethodInfo.MakeGenericMethod(params Type[])")]
#endif
    internal static Func<object, ValueTask<object?>> UnwrapperFor(Type resultType)
    {
        // This method creates a type-erased unwrapper for ValueTask<TResult>.
        // It uses reflection to create a delegate that can handle any TResult type.

        // TODO: AOT: This method is marked with RequiresDynamicCodeAttribute, which will not work well in NativeAOT
        // scenarios; the solution is to break this up into a Cached/Reflector version (like the MessageRouter does
        // with handlers), and SourceGenerate the UnwrapAndEraseAsync-equivalent method for each TResult type.

        // Note that this is only necessary because ValueTask<TResult> is a class-generic, rather than an interface
        // type, which means that the type cannot be co/contravariantly used (e.g. ValueTask<object?> is not a valid
        // supertype of ValueTask or ValueTask<T>, T != object?).

        MethodInfo createMethod =
            typeof(ValueTaskTypeErasure)
                .GetMethod(nameof(CreateErasingUnwrapper), BindingFlags.NonPublic | BindingFlags.Static)
                !.MakeGenericMethod(resultType);

        // Invoke createMethod (as static) to get the delegate.
        object? maybeUnwrapper = createMethod.Invoke(null, Array.Empty<object>());
        if (maybeUnwrapper is not Func<object, ValueTask<object?>> unwrapper)
        {
            throw new InvalidOperationException($"Expected a Func<object, ValueTask<object?>> delegate, but got {maybeUnwrapper?.GetType().Name ?? "null"}.");
        }

        return unwrapper;
    }
}
