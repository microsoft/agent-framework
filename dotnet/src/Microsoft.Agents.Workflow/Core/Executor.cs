// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
[DebuggerDisplay("{GetType().Name}{Id}({Name})")]
public abstract class Executor : IIdentified, IAsyncDisposable
{
    /// <summary>
    /// .
    /// </summary>
    public string Id { get; }

    /// <summary>
    /// .
    /// </summary>
    public string Name { get; }

    private Dictionary<string, object> State { get; } = new();

    /// <summary>
    /// .
    /// </summary>
    /// <param name="id"></param>
    /// <param name="name"></param>
    protected Executor(string? id = null, string? name = null)
    {
        this.Name = name ?? this.GetType().Name;
        this.Id = id ?? $"{this.Name}{Guid.NewGuid():N}";
    }

    /// <summary>
    /// Override this method to register handlers for the executor. The deafult implementation uses reflection to
    /// look for implementations of <see cref="IMessageHandler{TInput}"/> and <see cref="IMessageHandler{TInput, TResult}"/>.
    /// </summary>
    /// <param name="routeBuilder"></param>
    /// <returns></returns>
    protected virtual RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.ReflectHandlers(this);
    }

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
    /// .
    /// </summary>
    /// <param name="message"></param>
    /// <param name="context"></param>
    /// <returns></returns>
    /// <exception cref="NotSupportedException"></exception>
    /// <exception cref="TargetInvocationException"></exception>
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
    /// .
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// .
    /// </summary>
    public virtual ISet<Type> OutputTypes => new HashSet<Type>();

    /// <summary>
    /// .
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Router.CanHandle(messageType);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="context"></param>
    /// <returns></returns>
    public async ValueTask InitializeAsync(IWorkflowContext context)
    {
        if (this._initialized)
        {
            return;
        }

        await this.InitializeOverride(context).ConfigureAwait(false);

        this._initialized = true;
    }

    /// <summary>
    /// .
    /// </summary>
    public ExecutorCapabilities Capabilities
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            ExecutorType = this.GetType(),
            HandledMessageTypes = new HashSet<Type>(this.InputTypes),
            IsInitialized = this._initialized,
            StateKeys = new HashSet<string>(this.State.Keys)
        };

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    public ReadOnlyDictionary<string, object> CurrentState => new(this.State);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="state"></param>
    /// <exception cref="ArgumentNullException"></exception>
    public void RestoreState(IDictionary<string, object> state)
    {
        Throw.IfNull(state);

        this.State.Clear();

        foreach (KeyValuePair<string, object> kvp in state)
        {
            this.State[kvp.Key] = kvp.Value;
        }
    }

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual ValueTask PrepareForCheckpointAsync() => default;

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual ValueTask AfterCheckpointRestoreAsync() => default;

    /// <summary>
    /// .
    /// </summary>
    /// <param name="context"></param>
    /// <returns></returns>
    protected virtual ValueTask InitializeOverride(IWorkflowContext context) => default;

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual async ValueTask DisposeAsync()
    {
        this._initialized = false;
    }

    ValueTask IAsyncDisposable.DisposeAsync()
    {
        GC.SuppressFinalize(this); // Should we be suppressing the finalizer here? CodeAnalysis seems to want it (CA1816)

        // Chain to the virtual call to DisposeAsync.
        return this.DisposeAsync();
    }
}
