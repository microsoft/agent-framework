// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>Provides extensions for configuring <see cref="CallbackEnabledAgent"/> instances.</summary>
public static class CallbackEnabledAIAgentBuilderExtensions
{
    /// <summary>
    /// Adds callback support to the agent pipeline by wrapping the agent with a <see cref="CallbackEnabledAgent"/>.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/>.</param>
    /// <param name="configure">An optional callback that can be used to configure the <see cref="CallbackMiddlewareProcessor"/> instance.</param>
    /// <returns>The <paramref name="builder"/>.</returns>
    public static AIAgentBuilder UseCallbacks(this AIAgentBuilder builder, Action<CallbackMiddlewareProcessor>? configure = null)
        => Throw.IfNull(builder).Use((innerAgent, services) =>
        {
            var processor = new CallbackMiddlewareProcessor();
            configure?.Invoke(processor);

            return new CallbackEnabledAgent(innerAgent, processor);
        });

    /// <summary>
    /// Adds callback support to the agent pipeline by wrapping the agent with a <see cref="CallbackEnabledAgent"/>.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/>.</param>
    /// <param name="callbacks">The collection of <see cref="ICallbackMiddleware"/> instances to use.</param>
    /// <returns>The <paramref name="builder"/>.</returns>
    public static AIAgentBuilder UseCallbacks(this AIAgentBuilder builder, IEnumerable<ICallbackMiddleware> callbacks)
        => Throw.IfNull(builder).Use((innerAgent, services) =>
        {
            var processor = new CallbackMiddlewareProcessor(callbacks);
            return new CallbackEnabledAgent(innerAgent, processor);
        });
}
