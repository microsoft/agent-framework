// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for working with <see cref="IWorkflowContext"/> instances.
/// </summary>
public static class IWorkflowContextExtensions
{
    /// <summary>
    /// Invokes an asynchronous operation that reads, updates, and persists workflow state associated with the specified
    /// key.
    /// </summary>
    /// <typeparam name="TState">The type of the state object to read, update, and persist.</typeparam>
    /// <param name="context">The workflow context used to access and update state.</param>
    /// <param name="invocation">A delegate that receives the current state, workflow context, and cancellation token, and returns the updated
    /// state asynchronously.</param>
    /// <param name="key">The key identifying the state to read and update. Cannot be null or empty.</param>
    /// <param name="scopeName">An optional scope name that further qualifies the state key. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A ValueTask that represents the asynchronous operation.</returns>
    public static async ValueTask InvokeWithStateAsync<TState>(this IWorkflowContext context,
                                                               Func<TState?, IWorkflowContext, CancellationToken, ValueTask<TState?>> invocation,
                                                               string key,
                                                               string? scopeName = null,
                                                               CancellationToken cancellationToken = default)
    {
        TState? state = await context.ReadStateAsync<TState>(key, scopeName, cancellationToken).ConfigureAwait(false);
        state = await invocation(state, context, cancellationToken).ConfigureAwait(false);
        await context.QueueStateUpdateAsync(key, state, scopeName, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Invokes an asynchronous operation that reads, updates, and persists workflow state associated with the specified
    /// key.
    /// </summary>
    /// <typeparam name="TState">The type of the state object to read, update, and persist.</typeparam>
    /// <param name="context">The workflow context used to access and update state.</param>
    /// <param name="invocation">A delegate that receives the current state, workflow context, and cancellation token, and returns the updated
    /// state asynchronously.</param>
    /// <param name="key">The key identifying the state to read and update. Cannot be null or empty.</param>
    /// <param name="initialStateFactory">A factory to initialize state to if it is not set at the provided key.</param>
    /// <param name="scopeName">An optional scope name that further qualifies the state key. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A ValueTask that represents the asynchronous operation.</returns>
    public static async ValueTask InvokeWithStateAsync<TState>(this IWorkflowContext context,
                                                               Func<TState, IWorkflowContext, CancellationToken, ValueTask<TState?>> invocation,
                                                               string key,
                                                               Func<TState> initialStateFactory,
                                                               string? scopeName = null,
                                                               CancellationToken cancellationToken = default)
    {
        TState? state = await context.ReadOrInitStateAsync(key, initialStateFactory, scopeName, cancellationToken).ConfigureAwait(false);
        state = await invocation(state, context, cancellationToken).ConfigureAwait(false);
        await context.QueueStateUpdateAsync(key, state ?? initialStateFactory(), scopeName, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Queues a message to be sent to connected executors. The message will be sent during the next SuperStep.
    /// </summary>
    /// <param name="context">The workflow context used to access and update state.</param>
    /// <param name="message">The message to be sent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    public static ValueTask SendMessageAsync(this IWorkflowContext context, object message, CancellationToken cancellationToken = default) =>
        context.SendMessageAsync(message, null, cancellationToken);
}
