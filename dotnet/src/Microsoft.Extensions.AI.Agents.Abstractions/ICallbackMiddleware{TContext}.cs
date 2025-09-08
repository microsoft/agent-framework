// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines the contract for callback middleware that can intercept and process agent operations.
/// </summary>
/// <typeparam name="TContext">The type of context that this middleware operates on.</typeparam>
public interface ICallbackMiddleware<TContext> : ICallbackMiddleware
    where TContext : CallbackContext
{
    /// <summary>
    /// Determines whether the specified context type can be processed by the current instance.
    /// </summary>
    /// <typeparam name="TContextType">The type of the context to check.</typeparam>
    /// <returns><see langword="true"/> if the specified context type is assignable to the expected context type; otherwise, <see
    /// langword="false"/>.</returns>
    bool CanProcess<TContextType>();

    /// <summary>
    /// Processes the middleware with the specified context and next delegate.
    /// </summary>
    /// <param name="context">The context for the current operation.</param>
    /// <param name="next">The next middleware in the pipeline or the final operation.</param>
    /// <param name="cancellationToken">The cancellation token for the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    /// <remarks>
    /// Implementations should call the <paramref name="next"/> delegate to continue the pipeline,
    /// unless they want to short-circuit the execution. Middleware can perform operations before
    /// and after calling <paramref name="next"/> to implement cross-cutting concerns such as
    /// logging, authentication, caching, or error handling.
    /// </remarks>
    Task OnProcessAsync(TContext context, Func<TContext, Task> next, CancellationToken cancellationToken);
}
