// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Interface for actor state storage operations, providing persistence for actor state data.
/// </summary>
public interface IActorStateStorage
{
    /// <summary>
    /// Writes state changes to the actor's persistent storage.
    /// </summary>
    /// <param name="actorId">The identifier of the actor whose state is being modified.</param>
    /// <param name="operations">The collection of write operations to perform.</param>
    /// <param name="etag">The expected ETag for optimistic concurrency control.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the write response with success status and updated ETag.</returns>
    ValueTask<WriteResponse> WriteStateAsync(ActorId actorId, IReadOnlyCollection<ActorStateWriteOperation> operations, string etag, CancellationToken cancellationToken = default);

    /// <summary>
    /// Reads state data from the actor's persistent storage.
    /// </summary>
    /// <param name="actorId">The identifier of the actor whose state is being read.</param>
    /// <param name="operations">The collection of read operations to perform.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the read response with results and current ETag.</returns>
    ValueTask<ReadResponse> ReadStateAsync(ActorId actorId, IReadOnlyCollection<ActorStateReadOperation> operations, CancellationToken cancellationToken = default);
}
