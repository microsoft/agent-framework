// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// A manager for storing and retrieving workflow execution checkpoints.
/// </summary>
internal interface ICheckpointManager
{
    /// <summary>
    /// Commits the specified checkpoint and returns information that can be used to retrieve it later.
    /// </summary>
    /// <param name="checkpoint">The <see cref="Checkpoint"/> to be committed.</param>
    /// <returns>A <see cref="CheckpointInfo"/> representing the incoming checkpoint.</returns>
    ValueTask<CheckpointInfo> CommitCheckpointAsync(Checkpoint checkpoint);

    ValueTask<Checkpoint> LookupCheckpointAsync(CheckpointInfo checkpointInfo);
}
