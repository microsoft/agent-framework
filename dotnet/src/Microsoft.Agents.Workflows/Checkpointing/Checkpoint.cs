// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class Checkpoint
{
    [JsonConstructor]
    internal Checkpoint(
        int stepNumber,
        WorkflowInfo workflow,
        RunnerStateData runnerData,
        Dictionary<ScopeKey, PortableValue> stateData,
        Dictionary<EdgeId, PortableValue> edgeStateData,
        CheckpointInfo? parent = null)
    {
        this.StepNumber = Throw.IfLessThan(stepNumber, -1); // -1 is a special flag indicating the initial checkpoint.
        this.Workflow = Throw.IfNull(workflow);
        this.RunnerData = Throw.IfNull(runnerData);
        this.StateData = Throw.IfNull(stateData);
        this.EdgeStateData = Throw.IfNull(edgeStateData);
        this.Parent = parent;
    }

    [JsonIgnore]
    public bool IsInitial => this.StepNumber == -1;

    public int StepNumber { get; }
    public WorkflowInfo Workflow { get; }
    public RunnerStateData RunnerData { get; }

    public Dictionary<ScopeKey, PortableValue> StateData { get; } = [];
    public Dictionary<EdgeId, PortableValue> EdgeStateData { get; } = [];

    public CheckpointInfo? Parent { get; }
}
