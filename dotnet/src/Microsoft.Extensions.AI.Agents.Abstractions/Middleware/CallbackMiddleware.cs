// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base class for callback middleware implementations that provides common functionality.
/// </summary>
/// <typeparam name="TContext">The type of context that this middleware operates on.</typeparam>
public abstract class CallbackMiddleware<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TContext> : ICallbackMiddleware<TContext>
    where TContext : CallbackContext
{
    /// <inheritdoc/>
    public bool CanProcess(Type contextType)
        => contextType.IsAssignableFrom(typeof(TContext));

    /// <inheritdoc/>
    public Task OnProcessAsync(CallbackContext context, Func<CallbackContext, Task> next, CancellationToken cancellationToken)
    {
        if (context is not TContext typedContext)
        {
            throw new ArgumentException($"Invalid context type. Expected {typeof(TContext).FullName}, but received {context.GetType().FullName}.", nameof(context));
        }

        return OnProcessAsync(typedContext, ctx => next(ctx), cancellationToken);
    }

    /// <inheritdoc/>
    public bool CanProcess<TContextType>()
        => CanProcess(typeof(TContextType));

    /// <inheritdoc/>
    public abstract Task OnProcessAsync(TContext context, Func<TContext, Task> next, CancellationToken cancellationToken);
}
