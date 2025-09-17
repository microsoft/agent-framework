// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
    /// <param name="runId">The identifier for the current run or execution context.</param>
    /// <param name="checkpoint">The checkpoint to commit.</param>
    /// <returns>A <see cref="CheckpointInfo"/> representing the incoming checkpoint.</returns>
    ValueTask<CheckpointInfo> CommitCheckpointAsync(string runId, Checkpoint checkpoint);

    /// <summary>
    /// Retrieves the checkpoint associated with the specified checkpoint information.
    /// </summary>
    /// <param name="runId">The identifier for the current run of execution context.</param>
    /// <param name="checkpointInfo">The information used to identify the checkpoint.</param>
    /// <returns>A <see cref="ValueTask{TResult}"/> representing the asynchronous operation. The result contains the <see
    /// cref="Checkpoint"/> associated with the specified <paramref name="checkpointInfo"/>.</returns>
    /// <exception cref="KeyNotFoundException">Thrown if the checkpoint is not found.</exception>
    ValueTask<Checkpoint> LookupCheckpointAsync(string runId, CheckpointInfo checkpointInfo);
}
