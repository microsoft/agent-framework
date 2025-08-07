// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
[DebuggerDisplay("{GetType().Name}{Id}")]
public abstract class ExecutorBase : IIdentified, IAsyncDisposable
{
    /// <summary>
    /// A unique identifier for the executor.
    /// </summary>
    public string Id { get; }

    private Dictionary<string, object> State { get; } = new();

    /// <summary>
    /// Initialize the executor with a unique identifier
    /// </summary>
    /// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged
    /// UUID will be generated.</param>
    protected ExecutorBase(string? id = null)
    {
        this.Id = id ?? $"{this.GetType().Name}/{Guid.NewGuid():N}";
    }

    /// <summary>
    /// Override this method to register handlers for the executor. The deafult implementation uses reflection to
    /// look for implementations of <see cref="IMessageHandler{TInput}"/> and <see cref="IMessageHandler{TInput, TResult}"/>.
    /// </summary>
    protected abstract RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder);

    private MessageRouter? _router = null;
    internal MessageRouter Router
    {
        get
        {
            if (this._router == null)
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
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <returns>A ValueTask representing the asynchronous operation, wrapping the output from the executor.</returns>
    /// <exception cref="NotSupportedException">No handler found for the message type.</exception>
    /// <exception cref="TargetInvocationException">An exception is generated while handling the message.</exception>
    public async ValueTask<object?> ExecuteAsync(object message, IWorkflowContext context)
    {
        await context.AddEventAsync(new ExecutorInvokeEvent(this.Id)).ConfigureAwait(false);

        CallResult? result = await this.Router.RouteMessageAsync(message, context, requireRoute: true)
                                              .ConfigureAwait(false);

        ExecutorCompleteEvent completeEvent = new(this.Id)
        {
            Data = result == null ? null : result.IsSuccess ? result.Result : result.Exception
        };

        await context.AddEventAsync(completeEvent).ConfigureAwait(false);

        if (result == null)
        {
            throw new NotSupportedException(
                $"No handler found for message type {message.GetType().Name} in executor {this.GetType().Name}.");
        }

        if (!result.IsSuccess)
        {
            throw new TargetInvocationException($"Error invoking handler for {message.GetType()}", result.Exception!);
        }

        if (result.IsVoid)
        {
            return null; // Void result.
        }

        return result.Result;
    }

    private bool _initialized = false;

    /// <summary>
    /// Ensures that the executor has been initialized before performing operations.
    /// </summary>
    /// <remarks>This method checks the internal state of the executor and throws an exception if it has not
    /// been initialized. Call <c>InitializeAsync</c> before invoking any operations that require
    /// initialization.</remarks>
    /// <exception cref="InvalidOperationException">Thrown if the executor has not been initialized by calling <c>InitializeAsync</c>.</exception>
    protected void CheckInitialized()
    {
        if (!this._initialized)
        {
            throw new InvalidOperationException($"Executor {this.GetType().Name} is not initialized. Call InitializeAsync first.");
        }
    }

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can handle.
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can produce as output.
    /// </summary>
    public virtual ISet<Type> OutputTypes => new HashSet<Type>([typeof(object)]);

    /// <summary>
    /// Checks if the executor can handle a specific message type.
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Router.CanHandle(messageType);

    /// <inheritdoc cref="IAsyncDisposable.DisposeAsync"/>
    protected virtual async ValueTask DisposeAsync()
    {
        this._initialized = false;
    }

    /// <inheritdoc cref="IAsyncDisposable.DisposeAsync"/>
    ValueTask IAsyncDisposable.DisposeAsync()
    {
        GC.SuppressFinalize(this); // Should we be suppressing the finalizer here? CodeAnalysis seems to want it (CA1816)

        // Chain to the virtual call to DisposeAsync.
        return this.DisposeAsync();
    }
}

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
/// <typeparam name="TExecutor">The actual type of the <see cref="Executor{TExecutor}"/>.
/// This is used to reflectively discover handlers for messages without violating ILTrim requirements.
/// </typeparam>
public class Executor<
    [DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicMethods |
                                DynamicallyAccessedMemberTypes.NonPublicMethods |
                                DynamicallyAccessedMemberTypes.Interfaces)]
TExecutor
    > : ExecutorBase where TExecutor : Executor<TExecutor>
{
    /// <inheritdoc cref="ExecutorBase.ExecutorBase(string?)"/>
    protected Executor(string? id = null) : base(id)
    { }

    /// <inheritdoc />
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.ReflectHandlers<TExecutor>(this);
    }
}
