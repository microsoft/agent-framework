// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// .
/// </summary>
public sealed class CheckpointManager : ICheckpointManager
{
    private readonly Dictionary<CheckpointInfo, Checkpoint> _checkpoints = new();

    ValueTask<CheckpointInfo> ICheckpointManager.CommitCheckpointAsync(Checkpoint checkpoint)
    {
        Throw.IfNull(checkpoint);

        this._checkpoints[checkpoint] = checkpoint;
        return new(checkpoint);
    }

    ValueTask<Checkpoint> ICheckpointManager.LookupCheckpointAsync(CheckpointInfo checkpointInfo)
    {
        Throw.IfNull(checkpointInfo);

        if (!this._checkpoints.TryGetValue(checkpointInfo, out Checkpoint? checkpoint))
        {
            throw new KeyNotFoundException($"Checkpoint not found: {checkpointInfo}");
        }

        return new ValueTask<Checkpoint>(checkpoint);
    }
}
