// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Enables callback functionality for the specified <see cref="AIAgent"/> by configuring a callback middleware
/// processor.
/// </summary>
public static class CallbackEnabledAgentExtensions
{
    /// <summary>
    /// Wraps the specified <see cref="AIAgent"/> with a <see cref="CallbackEnabledAgent"/>, configuring it to use
    /// </summary>
    /// <param name="agent">The target agent to enable callbacks for.</param>
    /// <param name="builder">An optional action to configure the <see cref="CallbackMiddlewareProcessor"/>.</param>
    /// <returns>The <see cref="CallbackEnabledAgent"/> wrapper</returns>
    public static CallbackEnabledAgent WithCallbacks(this AIAgent agent, Action<CallbackMiddlewareProcessor>? builder = null)
    {
        _ = Throw.IfNull(agent);

        var processor = new CallbackMiddlewareProcessor();
        if (builder is not null)
        {
            builder(processor);
        }

        return new CallbackEnabledAgent(agent, processor);
    }
}
