// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows;

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

    private static readonly string s_namespace = typeof(Executor).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

    /// <summary>
    /// Initialize the executor with a unique identifier
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
    protected Executor(string id, ExecutorOptions? options = null)
    {
        this.Id = id;
        this.Options = options ?? ExecutorOptions.Default;
    }

    /// <summary>
    /// Gets the configuration options for the executor.
    /// </summary>
    protected ExecutorOptions Options { get; }

    /// <summary>
    /// Override this method to register handlers for the executor.
    /// </summary>
    protected abstract RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder);

    /// <summary>
    /// Override this method to declare the types of messages this executor can send.
    /// </summary>
    /// <returns></returns>
    protected virtual ISet<Type> ConfigureSentTypes() => new HashSet<Type>([typeof(object)]);

    /// <summary>
    /// Override this method to declare the types of messages this executor can yield as workflow outputs.
    /// </summary>
    /// <returns></returns>
    protected virtual ISet<Type> ConfigureYieldTypes()
    {
        if (this.Options.AutoYieldOutputHandlerResultObject)
        {
            return this.Router.DefaultOutputTypes;
        }

        return new HashSet<Type>();
    }

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
        using var activity = s_activitySource.StartActivity(ActivityNames.ExecutorProcess, ActivityKind.Internal);
        activity?.SetTag(Tags.ExecutorId, this.Id)
            .SetTag(Tags.ExecutorType, this.GetType().FullName)
            .SetTag(Tags.MessageType, messageType.TypeName)
            .CreateSourceLinks(context.TraceContext);

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
        if (result.Result is not null && this.Options.AutoSendMessageHandlerResultObject)
        {
            await context.SendMessageAsync(result.Result).ConfigureAwait(false);
        }
        if (result.Result is not null && this.Options.AutoYieldOutputHandlerResultObject)
        {
            await context.YieldOutputAsync(result.Result).ConfigureAwait(false);
        }

        return result.Result;
    }

    /// <summary>
    /// Invoked before a checkpoint is saved, allowing custom pre-save logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    protected internal virtual ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) => default;

    /// <summary>
    /// Invoked after a checkpoint is loaded, allowing custom post-load logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    protected internal virtual ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) => default;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can handle.
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can produce as output.
    /// </summary>
    public ISet<Type> OutputTypes { get; } = new HashSet<Type>([typeof(object)]);

    /// <summary>
    /// Checks if the executor can handle a specific message type.
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Router.CanHandle(messageType);

    internal bool CanHandle(TypeId messageType) => this.Router.CanHandle(messageType);

    internal bool CanOutput(Type messageType)
    {
        foreach (Type type in this.OutputTypes)
        {
            if (type.IsAssignableFrom(messageType))
            {
                return true;
            }
        }

        return false;
    }
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public abstract class Executor<TInput>(string id, ExecutorOptions? options = null)
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
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public abstract class Executor<TInput, TOutput>(string id, ExecutorOptions? options = null)
    : Executor(id, options ?? ExecutorOptions.Default),
      IMessageHandler<TInput, TOutput>
{
    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput, TOutput>(this.HandleAsync);

    /// <inheritdoc/>
    public abstract ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context);
}
