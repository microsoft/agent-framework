// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
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

    internal MessageRouter MessageRouter { get; init; }
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

        this.MessageRouter = MessageRouter.BindMessageHandlers(this, checkType: true);
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

        CallResult? result = await this.MessageRouter.RouteMessageAsync(message, context, requireRoute: true)
                                                     .ConfigureAwait(false);

        await context.AddEventAsync(new ExecutorCompleteEvent(this.Id)).ConfigureAwait(false);

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
    /// .
    /// </summary>
    public ISet<Type> InputTypes => this.MessageRouter.IncomingTypes;

    /// <summary>
    /// .
    /// </summary>
    [SuppressMessage("Design", "CA1065:Do not raise exceptions in unexpected locations", Justification = "<Pending>")]
    public ISet<Type> OutputTypes => throw new NotImplementedException();

    /// <summary>
    /// .
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.MessageRouter.CanHandle(messageType);

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
    protected virtual ValueTask PrepareForCheckpointAsync()
    {
        return default;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual ValueTask AfterCheckpointRestoreAsync()
    {
        return default;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="context"></param>
    /// <returns></returns>
    protected virtual ValueTask InitializeOverride(IWorkflowContext context)
    {
        // Default implementation does nothing.
        return default;
    }

    private async ValueTask FlushReduceRemainingAsync()
    {
        return;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual async ValueTask DisposeAsync()
    {
        this._initialized = false;

        await this.FlushReduceRemainingAsync().ConfigureAwait(false);
    }

    ValueTask IAsyncDisposable.DisposeAsync()
    {
        GC.SuppressFinalize(this); // Should we be suppressing the finalizer here? CodeAnalysis seems to want it (CA1816)

        // Chain to the virtual call to DisposeAsync.
        return this.DisposeAsync();
    }
}
