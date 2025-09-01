// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class Checkpoint : CheckpointInfo
{
    internal Checkpoint(
        int stepNumber,
        WorkflowInfo workflow,
        RunnerStateData runnerData,
        Dictionary<ScopeKey, ExportedState> stateData,
        Dictionary<EdgeConnection, ExportedState> edgeStateData)
    {
        this.StepNumber = Throw.IfLessThan(stepNumber, -1); // -1 is a special flag indicating the initial checkpoint.
        this.Workflow = Throw.IfNull(workflow);
        this.RunnerData = Throw.IfNull(runnerData);
        this.State = Throw.IfNull(stateData);
        this.EdgeState = Throw.IfNull(edgeStateData);
    }

    public bool IsInitial => this.StepNumber == -1;

    public int StepNumber { get; }
    public WorkflowInfo Workflow { get; }
    public RunnerStateData RunnerData { get; }

    public readonly Dictionary<ScopeKey, ExportedState> State = new();
    public readonly Dictionary<EdgeConnection, ExportedState> EdgeState = new();
}
