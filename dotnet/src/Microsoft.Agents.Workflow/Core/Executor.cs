// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// A tag interface for objects that have a unique identifier within an appropriate namespace.
/// </summary>
public interface IIdentified
{
    /// <summary>
    /// The unique identifier.
    /// </summary>
    string Id { get; }
}

/// <summary>
/// .
/// </summary>
public record ExecutorCapabilities
{
    /// <summary>
    /// .
    /// </summary>
    public string Id { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public string Name { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public Type ExecutorType { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public ISet<Type> HandledMessageTypes { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public bool IsInitialized { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public ISet<string> StateKeys { get; init; }

    /// <summary>
    /// .
    /// </summary>
    public ExecutorCapabilities()
    {
        this.Id = string.Empty;
        this.Name = string.Empty;
        this.ExecutorType = typeof(Executor);
        this.HandledMessageTypes = new HashSet<Type>();
        this.IsInitialized = false;
        this.StateKeys = new HashSet<string>();
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="id"></param>
    /// <param name="name"></param>
    /// <param name="executorType"></param>
    /// <param name="handledMessageTypes"></param>
    /// <param name="isInitialized"></param>
    /// <param name="stateKeys"></param>
    public ExecutorCapabilities(string id, string name, Type executorType, ISet<Type> handledMessageTypes, bool isInitialized, ISet<string> stateKeys)
    {
        this.Id = id;
        this.Name = name;
        this.ExecutorType = executorType;
        this.HandledMessageTypes = handledMessageTypes;
        this.IsInitialized = isInitialized;
        this.StateKeys = stateKeys;
    }
}

/// <summary>
/// .
/// </summary>
[DebuggerDisplay("{GetType().Name}{Id}({Name})")]
public abstract class Executor : DisposableObject, IIdentified
{
    /// <summary>
    /// .
    /// </summary>
    public string Id { get; }

    /// <summary>
    /// .
    /// </summary>
    public string Name { get; }

    private MessageRouter MessageRouter { get; init; }
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
    public async ValueTask<object?> ExecuteAsync(object message, IExecutionContext context)
    {
        CallResult? result = await this.MessageRouter.RouteMessageAsync(message, context, requireRoute: true)
                                                     .ConfigureAwait(false);

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
    public async ValueTask InitializeAsync(IExecutionContext context)
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
        if (state == null)
        {
            throw new ArgumentNullException(nameof(state), "State cannot be null.");
        }

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
        return CompletedValueTaskSource.Completed;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    protected virtual ValueTask AfterCheckpointRestoreAsync()
    {
        return CompletedValueTaskSource.Completed;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="context"></param>
    /// <returns></returns>
    protected virtual ValueTask InitializeOverride(IExecutionContext context)
    {
        // Default implementation does nothing.
        return CompletedValueTaskSource.Completed;
    }

    private async ValueTask FlushReduceRemainingAsync()
    {
        return;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="disposing"></param>
    /// <returns></returns>
    protected override async ValueTask DisposeAsync(bool disposing = false)
    {
        this._initialized = false;

        await this.FlushReduceRemainingAsync().ConfigureAwait(false);

        await base.DisposeAsync(disposing).ConfigureAwait(false);
    }
}
