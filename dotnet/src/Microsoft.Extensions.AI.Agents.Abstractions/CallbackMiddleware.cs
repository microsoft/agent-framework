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
        TContext typedContext;
        if (context is not TContext)
        {
            if (!this.CanProcess(typeof(TContext)))
            {
                throw new ArgumentException($"Invalid context type. Expected {typeof(TContext).FullName}, but received {context.GetType().FullName}.", nameof(context));
            }

            // If the type is a specialized type, we use it as the decorator of the starting pipeline context, providing it at initialization.
            // This should happen only at the first middleware in the chain.
            typedContext = (TContext)Activator.CreateInstance(typeof(TContext), context)!;
        }
        else
        {
            // If the type is exactly the same, use it directly.
            typedContext = (TContext)context;
        }

        return OnProcessAsync(typedContext, ctx => next(ctx), cancellationToken);
    }

    /// <inheritdoc/>
    public bool CanProcess<TContextType>()
        => CanProcess(typeof(TContextType));

    /// <inheritdoc/>
    public abstract Task OnProcessAsync(TContext context, Func<TContext, Task> next, CancellationToken cancellationToken);
}
