// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.InProc;

internal sealed class InProcStepTracer : IStepTracer
{
    private int _nextStepNumber = 0;

    public int StepNumber => this._nextStepNumber - 1;
    public bool StateUpdated { get; private set; } = false;
    public CheckpointInfo? Checkpoint { get; private set; } = null;

    public HashSet<string> Instantiated { get; } = [];
    public HashSet<string> Activated { get; } = [];

    public void TraceIntantiated(string executorId) => this.Instantiated.Add(executorId);
    public void TraceActivated(string executorId) => this.Activated.Add(executorId);
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

    public SuperStepCompletedEvent Complete(bool nextStepHasActions, bool hasPendingRequests)
    {
        return new SuperStepCompletedEvent(this.StepNumber, new SuperStepCompletionInfo(this.Activated, this.Instantiated)
        {
            HasPendingMessages = nextStepHasActions,
            HasPendingRequests = hasPendingRequests,
            StateUpdated = this.StateUpdated,
            Checkpoint = this.Checkpoint,
        });
    }

    public override string ToString()
    {
        StringBuilder sb = new();
        if (this.Instantiated.Count != 0)
        {
            sb.Append("Instantiated: ");
            sb.Append(string.Join(", ", this.Instantiated.OrderBy(id => id, StringComparer.Ordinal)));
            sb.AppendLine();
        }
        if (this.Activated.Count != 0)
        {
            sb.Append("Activated: ");
            sb.Append(string.Join(", ", this.Activated.OrderBy(id => id, StringComparer.Ordinal)));
            sb.AppendLine();
        }
        return sb.ToString();
    }
}
