// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Processes callback middleware chains for agent operations.
/// </summary>
public sealed class CallbackMiddlewareProcessor : ICallbackMiddlewareProcessor
{
    // For thread-safety when used as a Singleton
    private readonly ConcurrentBag<ICallbackMiddleware> _agentCallbacks = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="CallbackMiddlewareProcessor"/> class.
    /// </summary>
    /// <param name="callbacks">The collection of middleware for agent invocation operations.</param>
    public CallbackMiddlewareProcessor(IEnumerable<ICallbackMiddleware>? callbacks = null)
    {
        if (callbacks is not null)
        {
            foreach (var callback in callbacks)
            {
                AddCallback(callback);
            }
        }
    }

    /// <summary>
    /// Adds a middleware to the processor.
    /// </summary>
    /// <param name="middleware">The middleware to add.</param>
    public void AddCallback(ICallbackMiddleware middleware)
        => this._agentCallbacks.Add(middleware);

    /// <summary>
    /// Gets the middleware that can process the specified context type.
    /// </summary>
    /// <returns>A list of applicable middleware.</returns>
    internal IList<ICallbackMiddleware> GetCallbacksForContext(Type contextType)
        => this._agentCallbacks.Where(f => f.CanProcess(Throw.IfNull(contextType)))
            .Select(f => (ICallbackMiddleware)f)
            .ToArray();

    /// <summary>
    /// Processes the agent invocation through the middleware pipeline.
    /// </summary>
    /// <param name="context">The context for the agent invocation.</param>
    /// <param name="coreLogic">The core logic to execute after all middleware.</param>
    /// <param name="cancellationToken">The cancellation token for the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    private async Task ProcessAsync(CallbackContext context, Func<CallbackContext, Task> coreLogic, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);
        _ = Throw.IfNull(coreLogic);

        var applicable = this.GetCallbacksForContext(context.GetType());

        await this.InvokeChainAsync(context, applicable, 0, coreLogic, cancellationToken).ConfigureAwait(false);
    }

    internal async Task InvokeChainAsync(CallbackContext context, IList<ICallbackMiddleware> callbacks, int index, Func<CallbackContext, Task> coreLogic, CancellationToken cancellationToken)
    {
        if (index < callbacks.Count)
        {
            await callbacks[index].OnProcessAsync(
                context,
                async ctx => await this.InvokeChainAsync(ctx, callbacks, index + 1, coreLogic, cancellationToken).ConfigureAwait(false),
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await coreLogic(context).ConfigureAwait(false);
        }
    }
}

/// <summary>
/// Provides extension methods for the <see cref="CallbackMiddlewareProcessor"/> class.
/// </summary>
public static class CallbackMiddlewareProcessorExtensions
{
    /// <summary>
    /// Process the chain of existing callbacks for the given context type.
    /// </summary>
    /// <returns>The updated callback middleware processor.</returns>
    public static async Task ProcessAsync<TContext>(this CallbackMiddlewareProcessor processor,
        TContext context,
        Func<TContext, Task> coreLogic,
        CancellationToken cancellationToken)
        where TContext : CallbackContext
    {
        _ = Throw.IfNull(processor);
        _ = Throw.IfNull(context);
        _ = Throw.IfNull(coreLogic);

        var applicable = processor.GetCallbacksForContext<TContext>();

        await processor.InvokeChainAsync(context, applicable, 0, (callback) =>
            {
                var typedCallback = (callback as TContext)!;
                return coreLogic(typedCallback);
            }, cancellationToken)
            .ConfigureAwait(false);
    }

    /// <summary>
    /// Gets the middleware that can process the specified context type.
    /// </summary>
    /// <typeparam name="TContext">The context type.</typeparam>
    /// <returns>A list of applicable middleware.</returns>
    private static IList<ICallbackMiddleware> GetCallbacksForContext<TContext>(this CallbackMiddlewareProcessor processor)
        where TContext : CallbackContext
        => processor.GetCallbacksForContext(typeof(TContext));
}
