// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a base class for executors that maintain and manage state across multiple message handling operations.
/// </summary>
/// <typeparam name="TState">The type of state associated with this Executor.</typeparam>
public abstract class StatefulExecutor<TState> : Executor
{
    private readonly Func<TState> _initialStateFactory;

    private TState? _stateCache;

    /// <summary>
    /// Initializes the executor with a unique id and an initial value for the state.
    /// </summary>
    /// <param name="id">The unique identifier for this executor instance. Cannot be null or empty.</param>
    /// <param name="initialStateFactory">A factory to initialize the state value to be used by the executor.</param>
    /// <param name="options">Optional configuration settings for the executor. If null, default options are used.</param>
    /// <param name="declareCrossRunShareable">true to declare that the executor's state can be shared across multiple runs; otherwise, false.</param>
    protected StatefulExecutor(string id,
                               Func<TState> initialStateFactory,
                               StatefulExecutorOptions? options = null,
                               bool declareCrossRunShareable = false)
        : base(id, options ?? new StatefulExecutorOptions(), declareCrossRunShareable)
    {
        this.Options = (StatefulExecutorOptions)base.Options;
        this._initialStateFactory = Throw.IfNull(initialStateFactory);
    }

    /// <inheritdoc/>
    protected new StatefulExecutorOptions Options { get; }

    private string DefaultStateKey => $"{this.GetType().Name}.State";

    /// <summary>
    /// Gets the key used to identify the executor's state.
    /// </summary>
    protected string StateKey => this.Options.StateKey ?? this.DefaultStateKey;

    /// <summary>
    /// Reads the state associated with this executor. If it is not initialized, it will be set to the initial state.
    /// </summary>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="skipCache">Ignore the cached value, if any. State is not cached when running in Cross-Run Shareable
    /// mode.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns></returns>
    protected async ValueTask<TState> ReadStateAsync(IWorkflowContext context, bool skipCache = false, CancellationToken cancellationToken = default)
    {
        if (!skipCache && this._stateCache is not null)
        {
            return this._stateCache;
        }

        TState? state = await context.ReadOrInitStateAsync(this.StateKey, this._initialStateFactory, this.Options.ScopeName, cancellationToken)
                                     .ConfigureAwait(false);

        if (!context.ConcurrentRunsEnabled)
        {
            this._stateCache = state;
        }

        return state;
    }

    /// <summary>
    /// Queues up an update to the executor's state.
    /// </summary>
    /// <param name="state">The new value of state.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns></returns>
    protected ValueTask QueueStateUpdateAsync(TState state, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (!context.ConcurrentRunsEnabled)
        {
            this._stateCache = state;
        }

        return context.QueueStateUpdateAsync(this.StateKey, state, this.Options.ScopeName, cancellationToken);
    }

    /// <summary>
    /// Invokes an asynchronous operation that reads, updates, and persists workflow state associated with the specified
    /// key.
    /// </summary>
    /// <param name="invocation">A delegate that receives the current state, workflow context, and cancellation token,
    /// and returns the updated state asynchronously.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="skipCache">Ignore the cached value, if any. State is not cached when running in Cross-Run Shareable
    /// mode.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A ValueTask that represents the asynchronous operation.</returns>
    protected async ValueTask InvokeWithStateAsync(
        Func<TState, IWorkflowContext, CancellationToken, ValueTask<TState?>> invocation,
        IWorkflowContext context,
        bool skipCache = false,
        CancellationToken cancellationToken = default)
    {
        if (!skipCache && !context.ConcurrentRunsEnabled)
        {
            TState newState = await invocation(this._stateCache ?? (this._initialStateFactory()),
                                               context,
                                               cancellationToken).ConfigureAwait(false)
                           ?? this._initialStateFactory();

            await context.QueueStateUpdateAsync(this.StateKey,
                                                newState,
                                                this.Options.ScopeName,
                                                cancellationToken).ConfigureAwait(false);

            this._stateCache = newState;
        }
        else
        {
            await context.InvokeWithStateAsync(invocation,
                                               this.StateKey,
                                               this._initialStateFactory,
                                               this.Options.ScopeName,
                                               cancellationToken)
                         .ConfigureAwait(false);
        }
    }

    /// <inheritdoc cref="IResettableExecutor.ResetAsync"/>
    protected ValueTask ResetAsync()
    {
        this._stateCache = this._initialStateFactory();

        return default;
    }
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages,
/// and maintain state across invocations.
/// </summary>
/// <typeparam name="TState">The type of state associated with this Executor.</typeparam>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="initialStateFactory">A factory to initialize the state value to be used by the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class StatefulExecutor<TState, TInput>(string id, Func<TState> initialStateFactory, StatefulExecutorOptions? options = null, bool declareCrossRunShareable = false)
    : StatefulExecutor<TState>(id, initialStateFactory, options, declareCrossRunShareable), IMessageHandler<TInput>
{
    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput>(this.HandleAsync);

    /// <inheritdoc/>
    public abstract ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages,
/// and maintain state across invocations.
/// </summary>
/// <typeparam name="TState">The type of state associated with this Executor.</typeparam>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <typeparam name="TOutput">The type of output message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="initialStateFactory">A factory to initialize the state value to be used by the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class StatefulExecutor<TState, TInput, TOutput>(string id, Func<TState> initialStateFactory, StatefulExecutorOptions? options = null, bool declareCrossRunShareable = false)
    : StatefulExecutor<TState>(id, initialStateFactory, options, declareCrossRunShareable), IMessageHandler<TInput, TOutput>
{
    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput, TOutput>(this.HandleAsync);

    /// <inheritdoc/>
    public abstract ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);
}
