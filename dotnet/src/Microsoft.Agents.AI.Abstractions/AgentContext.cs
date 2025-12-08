// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides access to the current agent execution context.
/// </summary>
public static class AgentContext
{
    private static readonly AsyncLocal<AgentThread?> _currentThread = new();

    /// <summary>
    /// Gets the current agent thread for the executing operation.
    /// </summary>
    public static AgentThread? CurrentThread => _currentThread.Value;

    /// <summary>
    /// Sets the current agent thread for the scope of the returned disposable.
    /// </summary>
    /// <param name="thread">The thread to set as current.</param>
    /// <returns>A disposable that restores the previous thread when disposed.</returns>
    public static IDisposable SetCurrentThread(AgentThread? thread)
    {
        var previous = _currentThread.Value;
        _currentThread.Value = thread;
        return new DisposableAction(() => _currentThread.Value = previous);
    }

    private sealed class DisposableAction : IDisposable
    {
        private readonly Action _action;
        public DisposableAction(Action action) => _action = action;
        public void Dispose() => _action();
    }
}
