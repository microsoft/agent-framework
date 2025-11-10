// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Threading;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class TestRunState
{
    public ConcurrentDictionary<string, ConcurrentQueue<object>> SentMessages = new();
    public StateManager StateManager { get; } = new();
    public ConcurrentQueue<WorkflowEvent> EmittedEvents { get; } = new();
    public ConcurrentDictionary<string, ConcurrentQueue<object>> YieldedOutputs { get; } = new();

    private int _haltRequests;
    public int HaltRequests
    {
        get => Volatile.Read(ref this._haltRequests);
    }

    public void IncrementHaltRequests()
    {
        Interlocked.Increment(ref this._haltRequests);
    }

    public TestWorkflowContext ContextFor(string executorId) => new(executorId, this);
}
