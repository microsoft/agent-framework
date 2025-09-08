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
/// Manage callback middleware registration and chains of execution for agent middleware processing.
/// </summary>
public sealed class CallbackMiddlewareProcessor
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
    internal void AddCallback(ICallbackMiddleware middleware)
        => this._agentCallbacks.Add(middleware);

    /// <summary>
    /// Gets the middleware that can process the specified context type.
    /// </summary>
    /// <returns>A list of applicable middleware.</returns>
    internal IList<ICallbackMiddleware> GetCallbacksForContext(Type contextType)
    {
        Throw.IfNull(contextType);

        if (contextType.IsAssignableFrom(typeof(CallbackContext)))
        {
            throw new ArgumentException($"The context type provided must be a derived type of {nameof(CallbackContext)}.", nameof(contextType));
        }

        return this._agentCallbacks.Where(f => f.CanProcess(contextType))
            .Select(f => (ICallbackMiddleware)f)
            .ToArray();
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
}
