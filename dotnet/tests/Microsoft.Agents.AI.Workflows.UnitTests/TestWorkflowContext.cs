// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class TestWorkflowContext : IWorkflowContext
{
    private readonly string _executorId;
    private readonly TestRunState _state;

    public TestWorkflowContext(string executorId, TestRunState? state = null, bool concurrentRunsEnabled = false)
    {
        this._executorId = executorId;
        this._state = state ?? new TestRunState();

        this.ConcurrentRunsEnabled = concurrentRunsEnabled;
    }

    public bool ConcurrentRunsEnabled { get; }

    public ConcurrentQueue<object> SentMessages => this._state.SentMessages.GetOrAdd(this._executorId, _ => new());

    public StateManager StateManager => this._state.StateManager;

    public ConcurrentQueue<WorkflowEvent> EmittedEvents => this._state.EmittedEvents;

    public ConcurrentQueue<object> YieldedOutputs => this._state.YieldedOutputs.GetOrAdd(this._executorId, _ => new());

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
    {
        this.EmittedEvents.Enqueue(workflowEvent);
        return default;
    }

    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
    {
        this.YieldedOutputs.Enqueue(output);
        return this.AddEventAsync(new WorkflowOutputEvent(output, this._executorId), cancellationToken);
    }

    public ValueTask RequestHaltAsync()
    {
        this._state.IncrementHaltRequests();
        return default;
    }

    public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        => this.StateManager.ClearStateAsync(new ScopeId(this._executorId, scopeName));

    public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
        => this.StateManager.WriteStateAsync(new ScopeId(this._executorId, scopeName), key, value);

    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
        => this.StateManager.ReadStateAsync<T>(new ScopeId(this._executorId, scopeName), key);

    public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        => this.StateManager.ReadOrInitStateAsync(new ScopeId(this._executorId, scopeName), key, initialStateFactory);

    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        => this.StateManager.ReadKeysAsync(new ScopeId(this._executorId, scopeName));

    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
    {
        this.SentMessages.Enqueue(message);
        return default;
    }

    public IReadOnlyDictionary<string, string>? TraceContext => null;
}
