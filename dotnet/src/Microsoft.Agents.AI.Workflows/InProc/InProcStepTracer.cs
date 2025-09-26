// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.InProc;

internal sealed class InProcStepTracer : IStepTracer
{
    private int _nextStepNumber;

    public int StepNumber => this._nextStepNumber - 1;
    public bool StateUpdated { get; private set; }
    public CheckpointInfo? Checkpoint { get; private set; }

    public ConcurrentDictionary<string, string> Instantiated { get; } = new();
    public ConcurrentDictionary<string, string> Activated { get; } = new();

    public void TraceIntantiated(string executorId) => this.Instantiated.TryAdd(executorId, executorId);
    public void TraceActivated(string executorId) => this.Activated.TryAdd(executorId, executorId);
    public void TraceStatePublished() => this.StateUpdated = true;
    public void TraceCheckpointCreated(CheckpointInfo checkpoint) => this.Checkpoint = checkpoint;

    /// <summary>
    /// Reset the tracer to the specified step number.
    /// </summary>
    /// <param name="lastStepNumber">The Step Number of the last SuperStep. Note that Step Numbers are 0-indexed.</param>
    public void Reload(int lastStepNumber = 0) => this._nextStepNumber = lastStepNumber + 1;

    public SuperStepStartedEvent Advance(StepContext step)
    {
        this._nextStepNumber++;
        this.Activated.Clear();
        this.Instantiated.Clear();

        this.StateUpdated = false;
        this.Checkpoint = null;

        HashSet<string> sendingExecutors = [];
        bool hasExternalMessages = false;

        foreach (ExecutorIdentity identity in step.QueuedMessages.Keys)
        {
            if (identity == ExecutorIdentity.None)
            {
                hasExternalMessages = true;
            }
            else
            {
                sendingExecutors.Add(identity.Id!);
            }
        }

        return new SuperStepStartedEvent(this.StepNumber, new SuperStepStartInfo(sendingExecutors)
        {
            HasExternalMessages = hasExternalMessages
        });
    }

    public SuperStepCompletedEvent Complete(bool nextStepHasActions, bool hasPendingRequests) => new(this.StepNumber, new SuperStepCompletionInfo(this.Activated.Keys, this.Instantiated.Keys)
    {
        HasPendingMessages = nextStepHasActions,
        HasPendingRequests = hasPendingRequests,
        StateUpdated = this.StateUpdated,
        Checkpoint = this.Checkpoint,
    });

    public override string ToString()
    {
        StringBuilder sb = new();

        if (this.Instantiated.Keys.Count != 0)
        {
            sb.Append("Instantiated: ").Append(string.Join(", ", this.Instantiated.Keys.OrderBy(id => id, StringComparer.Ordinal)));
        }

        if (this.Activated.Keys.Count != 0)
        {
            if (sb.Length != 0)
            {
                sb.AppendLine();
            }

            sb.Append("Activated: ").Append(string.Join(", ", this.Activated.Keys.OrderBy(id => id, StringComparer.Ordinal)));
        }

        return sb.ToString();
    }
}
