// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Prepares a workflow-backed <see cref="AgentSession"/> to continue from a workflow checkpoint.
/// </summary>
/// <remarks>
/// <para>
/// Retrieve this service from a workflow-backed session with
/// <c>session.GetService&lt;WorkflowSessionCheckpointRecovery&gt;()</c>. Other session types return
/// <see langword="null"/>.
/// </para>
/// <para>
/// This service prepares recovery of an interrupted run. It is not a general rollback mechanism.
/// The selected checkpoint must belong to the same serialized session state, workflow definition,
/// and checkpoint store. Selecting an older checkpoint can repeat external effects.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class WorkflowSessionCheckpointRecovery
{
    private readonly WorkflowSession _session;

    internal WorkflowSessionCheckpointRecovery(WorkflowSession session)
    {
        this._session = session;
    }

    /// <summary>
    /// Gets the checkpoint currently selected by the workflow session.
    /// </summary>
    public CheckpointInfo? CurrentCheckpoint => this._session.LastCheckpoint;

    /// <summary>
    /// Prepares the session to continue the work queued in a workflow checkpoint without starting
    /// a new user turn.
    /// </summary>
    /// <param name="checkpointId">
    /// The checkpoint identifier to select. When <see langword="null"/>, the session keeps its
    /// current checkpoint.
    /// </param>
    /// <returns>
    /// <see langword="true"/> when a checkpoint is available for recovery; otherwise
    /// <see langword="false"/>.
    /// </returns>
    public bool TryPrepare(string? checkpointId = null) =>
        this._session.TryPrepareCheckpointRecovery(checkpointId);
}
