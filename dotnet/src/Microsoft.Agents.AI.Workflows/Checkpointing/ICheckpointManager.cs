// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// A manager for storing and retrieving workflow execution checkpoints.
/// </summary>
internal interface ICheckpointManager
{
    /// <summary>
    /// Commits the specified checkpoint and returns information that can be used to retrieve it later.
    /// </summary>
    /// <param name="sessionId">The identifier for the current session or execution context.</param>
    /// <param name="checkpoint">The checkpoint to commit.</param>
    /// <returns>A <see cref="CheckpointInfo"/> representing the incoming checkpoint.</returns>
    ValueTask<CheckpointInfo> CommitCheckpointAsync(string sessionId, Checkpoint checkpoint);

    /// <summary>
    /// Retrieves the checkpoint associated with the specified checkpoint information.
    /// </summary>
    /// <param name="sessionId">The identifier for the current session of execution context.</param>
    /// <param name="checkpointInfo">The information used to identify the checkpoint.</param>
    /// <returns>A <see cref="ValueTask{TResult}"/> representing the asynchronous operation. The result contains the <see
    /// cref="Checkpoint"/> associated with the specified <paramref name="checkpointInfo"/>.</returns>
    /// <exception cref="KeyNotFoundException">Thrown if the checkpoint is not found.</exception>
    ValueTask<Checkpoint> LookupCheckpointAsync(string sessionId, CheckpointInfo checkpointInfo);

    /// <summary>
    /// Asynchronously retrieves the collection of checkpoint information for the specified session identifier, optionally
    /// filtered by a parent checkpoint.
    /// </summary>
    /// <param name="sessionId">The unique identifier of the session for which to retrieve checkpoint information. Cannot be null or empty.</param>
    /// <param name="withParent">An optional parent checkpoint to filter the results. If specified, only checkpoints with the given parent are
    /// returned; otherwise, all checkpoints for the session are included.</param>
    /// <returns>A value task representing the asynchronous operation. The result contains a collection of <see
    /// cref="CheckpointInfo"/> objects associated with the specified session. The collection is empty if no checkpoints are
    /// found.</returns>
    ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null);

    /// <summary>
    /// Notifies the underlying store that a workflow was successfully restored from the specified checkpoint, so that
    /// a store deferring work until then can carry it out.
    /// </summary>
    /// <param name="sessionId">The identifier for the current session or execution context.</param>
    /// <param name="checkpointInfo">Identifies the checkpoint the workflow was restored from.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// <see langword="true"/> when the store observed the notification and may therefore have changed which
    /// checkpoints it holds; otherwise <see langword="false"/>. Callers that cache the checkpoint index use this to
    /// decide whether the cached copy needs to be read again.
    /// </returns>
    ValueTask<bool> NotifyCheckpointRestoredAsync(string sessionId, CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default);
}
