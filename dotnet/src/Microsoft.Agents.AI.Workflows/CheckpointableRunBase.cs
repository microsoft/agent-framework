// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a base object for a workflow run that may support checkpointing.
/// </summary>
public abstract class CheckpointableRunBase
{
    // TODO: Rename Context?
    private readonly ICheckpointingHandle _checkpointingHandle;

    internal CheckpointableRunBase(ICheckpointingHandle checkpointingHandle)
    {
        this._checkpointingHandle = checkpointingHandle;
    }

    /// <inheritdoc cref="ICheckpointingHandle.IsCheckpointingEnabled"/>
    public bool IsCheckpointingEnabled => this._checkpointingHandle.IsCheckpointingEnabled;

    /// <inheritdoc cref="ICheckpointingHandle.Checkpoints"/>
    public IReadOnlyList<CheckpointInfo> Checkpoints => this._checkpointingHandle.Checkpoints ?? [];

    /// <summary>
    /// Gets the most recent checkpoint information.
    /// </summary>
    public CheckpointInfo? LastCheckpoint
    {
        get
        {
            if (!this.IsCheckpointingEnabled)
            {
                return null;
            }

            var checkpoints = this.Checkpoints;
            return checkpoints.Count > 0 ? checkpoints[checkpoints.Count - 1] : null;
        }
    }

    /// <inheritdoc cref="ICheckpointingHandle.RestoreCheckpointAsync"/>
    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
        => this._checkpointingHandle.RestoreCheckpointAsync(checkpointInfo, cancellationToken);
}
