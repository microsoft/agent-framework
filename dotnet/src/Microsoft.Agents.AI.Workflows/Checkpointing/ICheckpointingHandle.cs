// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal interface ICheckpointingHandle
{
    /// <summary>
    /// Gets a value indicating whether checkpointing is enabled for the current operation or process.
    /// </summary>
    bool IsCheckpointingEnabled { get; }

    /// <summary>
    /// Gets a read-only list of checkpoint information associated with the current context.
    /// </summary>
    IReadOnlyList<CheckpointInfo> Checkpoints { get; }

    /// <summary>
    /// Restores the system state from the specified checkpoint asynchronously.
    /// </summary>
    /// <param name="checkpointInfo">The checkpoint information that identifies the state to restore. Cannot be null.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the restore operation.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous restore operation.</returns>
    ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default);
}
