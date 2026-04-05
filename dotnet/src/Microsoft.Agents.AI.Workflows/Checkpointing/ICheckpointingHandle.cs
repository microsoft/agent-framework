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
    /// <remarks>
    /// This contract is used by live runtime restore paths. Implementations may re-emit pending
    /// external request events as part of the restore once the active event stream is ready to
    /// observe them.
    ///
    /// Initial resume paths that create a new event stream should restore state first and defer
    /// any replay until after the subscriber is attached, rather than calling this contract
    /// directly before the stream is ready.
    /// </remarks>
    /// <param name="checkpointInfo">The checkpoint information that identifies the state to restore. Cannot be null.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the restore operation.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous restore operation.</returns>
    ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default);
}
