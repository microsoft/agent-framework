// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides access to the current agent execution context.
/// </summary>
public static class AgentContext
{
    private class ContextState
    {
        public AgentThread? Thread { get; init; }
        public string? ContextId { get; init; }
        public AdditionalPropertiesDictionary? AdditionalProperties { get; init; }
    }

    private static readonly AsyncLocal<ContextState?> _current = new();

    /// <summary>
    /// Gets the current agent thread for the executing operation.
    /// </summary>
    public static AgentThread? CurrentThread => _current.Value?.Thread;

    /// <summary>
    /// Gets the current context ID (e.g., session ID, correlation ID).
    /// </summary>
    public static string? ContextId => _current.Value?.ContextId;

    /// <summary>
    /// Gets the additional properties associated with the current execution context.
    /// </summary>
    public static AdditionalPropertiesDictionary? AdditionalProperties => _current.Value?.AdditionalProperties;

    /// <summary>
    /// Sets the current agent thread for the scope of the returned disposable.
    /// </summary>
    /// <param name="thread">The thread to set as current.</param>
    /// <returns>A disposable that restores the previous thread when disposed.</returns>
    public static IDisposable SetCurrentThread(AgentThread? thread)
    {
        return BeginScope(thread: thread);
    }

    /// <summary>
    /// Begins a new execution scope with the specified context data.
    /// </summary>
    /// <param name="contextId">The context ID.</param>
    /// <param name="thread">The agent thread.</param>
    /// <param name="additionalProperties">The additional properties.</param>
    /// <returns>A disposable object that restores the previous context when disposed.</returns>
    public static IDisposable BeginScope(string? contextId = null, AgentThread? thread = null, AdditionalPropertiesDictionary? additionalProperties = null)
    {
        var parent = _current.Value;
        _current.Value = new ContextState
        {
            Thread = thread ?? parent?.Thread,
            ContextId = contextId ?? parent?.ContextId,
            AdditionalProperties = additionalProperties ?? parent?.AdditionalProperties?.Clone()
        };
        return new DisposableAction(() => _current.Value = parent);
    }

    private sealed class DisposableAction : IDisposable
    {
        private readonly Action _action;
        public DisposableAction(Action action) => _action = action;
        public void Dispose() => _action();
    }
}
