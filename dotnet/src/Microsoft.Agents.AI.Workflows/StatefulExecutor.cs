// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CS0618 // Type or member is obsolete - Internal use of obsolete types for backward compatibility

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a base class for executors that maintain and manage state across multiple message handling operations.
/// </summary>
/// <remarks>
/// State is read from the current workflow context, including pending updates and restored checkpoints.
/// Derived executors with instance state must explicitly implement <see cref="IResettableExecutor"/>
/// to support resetting that state between runs.
/// </remarks>
/// <typeparam name="TState">The type of state associated with this Executor.</typeparam>
public abstract class StatefulExecutor<TState> : Executor
{
    private readonly Func<TState> _initialStateFactory;

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
    /// <param name="skipCache">Retained for compatibility. State is always read from the workflow context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns></returns>
    protected ValueTask<TState> ReadStateAsync(IWorkflowContext context, bool skipCache = false, CancellationToken cancellationToken = default)
        => context.ReadOrInitStateAsync(this.StateKey, this._initialStateFactory, this.Options.ScopeName, cancellationToken);

    /// <summary>
    /// Queues up an update to the executor's state.
    /// </summary>
    /// <param name="state">The new value of state.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns></returns>
    protected ValueTask QueueStateUpdateAsync(TState state, IWorkflowContext context, CancellationToken cancellationToken = default)
        => context.QueueStateUpdateAsync(this.StateKey, state, this.Options.ScopeName, cancellationToken);

    /// <summary>
    /// Invokes an asynchronous operation that reads, updates, and persists workflow state associated with the specified
    /// key.
    /// </summary>
    /// <param name="invocation">A delegate that receives the current state, workflow context, and cancellation token,
    /// and returns the updated state asynchronously.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="skipCache">Retained for compatibility. State is always read from the workflow context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A ValueTask that represents the asynchronous operation.</returns>
    protected ValueTask InvokeWithStateAsync(
        Func<TState, IWorkflowContext, CancellationToken, ValueTask<TState?>> invocation,
        IWorkflowContext context,
        bool skipCache = false,
        CancellationToken cancellationToken = default)
        => context.InvokeWithStateAsync(invocation,
                                        this.StateKey,
                                        this._initialStateFactory,
                                        this.Options.ScopeName,
                                        cancellationToken);

    /// <inheritdoc cref="IResettableExecutor.ResetAsync"/>
    /// <remarks>
    /// The base implementation has no instance state to reset and does not change persisted workflow state.
    /// Derived executors can override this method to reset their own instance state.
    /// </remarks>
    protected virtual ValueTask ResetAsync() => default;
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
/// <param name="sentMessageTypes">Message types sent by the handler. Defaults to empty, and will filter out non-matching messages.</param>
/// <param name="outputTypes">Message types yielded as output by the handler. Defaults to empty.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class StatefulExecutor<TState, TInput>(string id,
    Func<TState> initialStateFactory,
    StatefulExecutorOptions? options = null,
    IEnumerable<Type>? sentMessageTypes = null,
    IEnumerable<Type>? outputTypes = null,
    bool declareCrossRunShareable = false)
    : StatefulExecutor<TState>(id, initialStateFactory, options, declareCrossRunShareable), IMessageHandler<TInput>
{
    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask> handlerDelegate = this.HandleAsync;

        return protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler(handlerDelegate))
                              .AddMethodAttributeTypes(handlerDelegate.Method)
                              .AddClassAttributeTypes(this.GetType())
                              .SendsMessageTypes(sentMessageTypes ?? [])
                              .YieldsOutputTypes(outputTypes ?? []);
    }

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
/// <param name="sentMessageTypes">Message types sent by the handler. Defaults to empty, and will filter out non-matching messages.</param>
/// <param name="outputTypes">Message types yielded as output by the handler. Defaults to empty.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class StatefulExecutor<TState, TInput, TOutput>(string id,
    Func<TState> initialStateFactory,
    StatefulExecutorOptions? options = null,
    IEnumerable<Type>? sentMessageTypes = null,
    IEnumerable<Type>? outputTypes = null,
    bool declareCrossRunShareable = false)
    : StatefulExecutor<TState>(id, initialStateFactory, options, declareCrossRunShareable), IMessageHandler<TInput, TOutput>
    where TOutput : notnull
{
    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> handlerDelegate = this.HandleAsync;
        return protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler(handlerDelegate))
                              .AddMethodAttributeTypes(handlerDelegate.Method)
                              .AddClassAttributeTypes(this.GetType())
                              .SendsMessageTypes(sentMessageTypes ?? [])
                              .YieldsOutputTypes(outputTypes ?? []);
    }

    /// <inheritdoc/>
    public abstract ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);
}
