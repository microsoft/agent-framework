// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

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

    /// <summary>
    /// Adds a <see cref="AgentInvokeCallbackContext"/> middleware to the <see cref="CallbackMiddlewareProcessor"/>.
    /// </summary>
    /// <param name="processor">The <see cref="CallbackMiddlewareProcessor"/> to which the middleware will be added. Cannot be <see
    /// langword="null"/>.</param>
    /// <param name="middleware">The callback middleware to add. Cannot be <see langword="null"/>.</param>
    public static CallbackMiddlewareProcessor AddCallback(this CallbackMiddlewareProcessor processor, ICallbackMiddleware<AgentInvokeCallbackContext> middleware)
        => processor.AddCallback(Throw.IfNull(middleware));

    /// <summary>
    /// Adds a callback middleware to the specified <see cref="CallbackMiddlewareProcessor"/>.
    /// </summary>
    /// <param name="processor">The <see cref="CallbackMiddlewareProcessor"/> to which the middleware will be added. Cannot be <see
    /// langword="null"/>.</param>
    /// <param name="middleware">The callback middleware to add. Cannot be <see langword="null"/>.</param>
    public static CallbackMiddlewareProcessor AddCallback(this CallbackMiddlewareProcessor processor, ICallbackMiddleware<OtherCallbackContext> middleware)
        => processor.AddCallback(Throw.IfNull(middleware));
}
