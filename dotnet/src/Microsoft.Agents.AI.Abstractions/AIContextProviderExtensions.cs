// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods for the <see cref="AIContextProvider"/> class.
/// </summary>
public static class AIContextProviderExtensions
{
    /// <summary>
    /// Adds message filtering to an existing <see cref="AIContextProvider"/>, so that data passed to to and from it
    /// can be filtered, updated or replaced.
    /// </summary>
    /// <param name="innerAIContextProvider">The underlying AI context provider to be wrapped. Cannot be null.</param>
    /// <param name="invokingContextFilter">An optional filter function to apply to the AI context before it is returned. If null, no filter is applied at this
    /// stage.</param>
    /// <param name="invokedContextFilter">An optional filter function to apply to the invocation context before it is consumed. If null, no
    /// filter is applied at this stage.</param>
    /// <returns>The <see cref="AIContextProvider"/> with filtering applied.</returns>
    public static AIContextProvider WithMessageFilters(
        this AIContextProvider innerAIContextProvider,
        Func<AIContext, AIContext>? invokingContextFilter = null,
        Func<AIContextProvider.InvokedContext, AIContextProvider.InvokedContext>? invokedContextFilter = null)
    {
        return new MessageFilteringAIContextProvider(
            innerAIContextProvider,
            invokingContextFilter,
            invokedContextFilter);
    }

    /// <summary>
    /// Decorates the provided <see cref="AIContextProvider"/> so that it does not receive messages produced by any <see cref="AIContextProvider"/>.
    /// </summary>
    /// <param name="innerAIContextProvider">The underlying AI context provider to add the filter to. Cannot be null.</param>
    /// <returns>A new <see cref="AIContextProvider"/> instance that filters out <see cref="AIContextProvider"/> messages.</returns>
    public static AIContextProvider WithAIContextProviderMessageRemoval(this AIContextProvider innerAIContextProvider)
    {
        return new MessageFilteringAIContextProvider(
            innerAIContextProvider,
            invokedContextFilter: (ctx) =>
            {
                ctx.AIContextProviderMessages = null;
                return ctx;
            });
    }
}
