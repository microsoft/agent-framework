// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Provides the runtime context for an actor, enabling it to interact with the actor system.
/// </summary>
public interface IActorRuntimeContext
{
    /// <summary>
    /// Gets the identifier of the actor.
    /// </summary>
    ActorId ActorId { get; }

    /// <summary>
    /// Watches for incoming requests and responses in the actor's inbox and outbox.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of actor notifications.</returns>
    IAsyncEnumerable<ActorMessage> WatchMessagesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Performs a batch of write operations atomically.
    /// </summary>
    /// <param name="operations">The batch of write operations to perform.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task representing the write response.</returns>
    ValueTask<WriteResponse> WriteAsync(ActorWriteOperationBatch operations, CancellationToken cancellationToken = default);

    /// <summary>
    /// Performs a batch of read operations.
    /// </summary>
    /// <param name="operations">The batch of read operations to perform.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task representing the read response.</returns>
    ValueTask<ReadResponse> ReadAsync(ActorReadOperationBatch operations, CancellationToken cancellationToken = default);

    /// <summary>
    /// Reports progress updates for streaming responses.
    /// The messageId must correspond to a non-terminated request in the actor's inbox (Status is Pending).
    /// </summary>
    /// <param name="messageId">The identifier of the message being updated.</param>
    /// <param name="sequenceNumber">The sequence number for ordering progress updates.</param>
    /// <param name="data">The progress data.</param>
    void OnProgressUpdate(string messageId, int sequenceNumber, JsonElement data);
}
