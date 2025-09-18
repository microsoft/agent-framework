// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
[DebuggerDisplay("{GetType().Name}{Id}")]
public abstract class Executor : IIdentified
{
    /// <summary>
    /// A unique identifier for the executor.
    /// </summary>
    public string Id { get; }

    private readonly ExecutorOptions _options;

    /// <summary>
    /// Initialize the executor with a unique identifier
    /// </summary>
    /// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged UUID will be generated.</param>
    /// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
    protected Executor(string? id = null, ExecutorOptions? options = null)
    {
        this.Id = id ?? $"{this.GetType().Name}/{Guid.NewGuid():N}";
        this._options = options ?? ExecutorOptions.Default;
    }

    /// <summary>
    /// Override this method to register handlers for the executor.
    /// </summary>
    protected abstract RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder);

    private MessageRouter? _router;
    internal MessageRouter Router
    {
        get
        {
            if (this._router is null)
            {
                RouteBuilder routeBuilder = this.ConfigureRoutes(new RouteBuilder());
                this._router = routeBuilder.Build();
            }

            return this._router;
        }
    }

    /// <summary>
    /// Process an incoming message using the registered handlers.
    /// </summary>
    /// <param name="message">The message to be processed by the executor.</param>
    /// <param name="messageType">The "declared" type of the message (captured when it was being sent). This is
    /// used to enable routing messages as their base types, in absence of true polymorphic type routing.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <returns>A ValueTask representing the asynchronous operation, wrapping the output from the executor.</returns>
    /// <exception cref="NotSupportedException">No handler found for the message type.</exception>
    /// <exception cref="TargetInvocationException">An exception is generated while handling the message.</exception>
    public async ValueTask<object?> ExecuteAsync(object message, TypeId messageType, IWorkflowContext context)
    {
        await context.AddEventAsync(new ExecutorInvokedEvent(this.Id, message)).ConfigureAwait(false);

        CallResult? result = await this.Router.RouteMessageAsync(message, context, requireRoute: true)
                                              .ConfigureAwait(false);

        ExecutorEvent executionResult;
        if (result?.IsSuccess is not false)
        {
            executionResult = new ExecutorCompletedEvent(this.Id, result?.Result);
        }
        else
        {
            executionResult = new ExecutorFailedEvent(this.Id, result.Exception);
        }

        await context.AddEventAsync(executionResult).ConfigureAwait(false);

        if (result is null)
        {
            throw new NotSupportedException(
                $"No handler found for message type {message.GetType().Name} in executor {this.GetType().Name}.");
        }

        if (!result.IsSuccess)
        {
            throw new TargetInvocationException($"Error invoking handler for {message.GetType()}", result.Exception);
        }

        if (result.IsVoid)
        {
            return null; // Void result.
        }

        // If we had a real return type, raise it as a SendMessage; TODO: Should we have a way to disable this behaviour?
        if (result.Result is not null && this._options.AutoSendMessageHandlerResultObject)
        {
            await context.SendMessageAsync(result.Result).ConfigureAwait(false);
        }

        return result.Result;
    }

    /// <summary>
    /// Invoked before a checkpoint is saved, allowing custom pre-save logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellation"></param>
    protected internal virtual ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default) => default;

    /// <summary>
    /// Invoked after a checkpoint is loaded, allowing custom post-load logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellation"></param>
    protected internal virtual ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default) => default;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can handle.
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can produce as output.
    /// </summary>
    public virtual ISet<Type> OutputTypes { get; } = new HashSet<Type>([typeof(object)]);

    /// <summary>
    /// Checks if the executor can handle a specific message type.
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Router.CanHandle(messageType);

    internal bool CanHandle(TypeId messageType) => this.Router.CanHandle(messageType);
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged UUID will be generated.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public abstract class Executor<TInput>(string? id = null, ExecutorOptions? options = null)
    : Executor(id, options), IMessageHandler<TInput>
{
    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput>(this.HandleAsync);

    /// <inheritdoc/>
    public abstract ValueTask HandleAsync(TInput message, IWorkflowContext context);
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <typeparam name="TOutput">The type of output message.</typeparam>
/// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged UUID will be generated.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public abstract class Executor<TInput, TOutput>(string? id = null, ExecutorOptions? options = null)
    : Executor(id, options ?? ExecutorOptions.Default),
      IMessageHandler<TInput, TOutput>
{
    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput, TOutput>(this.HandleAsync);

    /// <inheritdoc/>
    public abstract ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context);
}
