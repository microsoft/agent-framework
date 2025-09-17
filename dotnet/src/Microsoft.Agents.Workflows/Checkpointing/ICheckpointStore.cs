// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Defines a contract for storing and retrieving checkpoints associated with a specific run and key.
/// </summary>
/// <remarks>Implementations of this interface enable durable or in-memory storage of checkpoints, which can be
/// used to resume or audit long-running processes. The interface is generic to support different storage object types
/// depending on the application's requirements.</remarks>
/// <typeparam name="TStoreObject">The type of object to be stored as the value for each checkpoint.</typeparam>
public interface ICheckpointStore<TStoreObject>
{
    /// <summary>
    /// Asynchronously retrieves the collection of checkpoint information for the specified run identifier, optionally
    /// filtered by a parent checkpoint.
    /// </summary>
    /// <param name="runId">The unique identifier of the run for which to retrieve checkpoint information. Cannot be null or empty.</param>
    /// <param name="withParent">An optional parent checkpoint to filter the results. If specified, only checkpoints with the given parent are
    /// returned; otherwise, all checkpoints for the run are included.</param>
    /// <returns>A value task representing the asynchronous operation. The result contains a collection of <see
    /// cref="CheckpointInfo"/> objects associated with the specified run. The collection is empty if no checkpoints are
    /// found.</returns>
    ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null);

    /// <summary>
    /// Asynchronously creates a checkpoint for the specified run and key, associating it with the provided value and
    /// optional parent checkpoint.
    /// </summary>
    /// <param name="runId">The unique identifier of the run for which the checkpoint is being created. Cannot be null or empty.</param>
    /// <param name="value">The value to associate with the checkpoint. Cannot be null.</param>
    /// <param name="parent">The optional parent checkpoint information. If specified, the new checkpoint will be linked as a child of this
    /// parent.</param>
    /// <returns>A ValueTask that represents the asynchronous operation. The result contains the <see cref="CheckpointInfo"/>
    /// object representing this stored checkpoint.</returns>
    ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, TStoreObject value, CheckpointInfo? parent = null);

    /// <summary>
    /// Asynchronously retrieves a checkpoint object associated with the specified run and checkpoint key.
    /// </summary>
    /// <param name="runId">The unique identifier of the run for which the checkpoint is to be retrieved. Cannot be null or empty.</param>
    /// <param name="key">The key identifying the specific checkpoint to retrieve. Cannot be null.</param>
    /// <returns>A ValueTask that represents the asynchronous operation. The result contains the checkpoint object associated
    /// with the specified run and key.</returns>
    ValueTask<TStoreObject> RetrieveCheckpointAsync(string runId, CheckpointInfo key);
}
