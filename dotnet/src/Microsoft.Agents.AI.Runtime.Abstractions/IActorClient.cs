// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Interface for sending requests to actors and managing responses.
/// </summary>
public interface IActorClient
{
    /// <summary>
    /// Submits a request to an actor and gets a handle for the response.
    /// This method is idempotent: if the request is already in progress, it will return the existing response.
    /// </summary>
    /// <param name="request">The request to send to the actor.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the actor response handle.</returns>
    ValueTask<ActorResponseHandle> SendRequestAsync(ActorRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Gets an already-running request by its identifier.
    /// </summary>
    /// <param name="actorId">The identifier of the actor processing the request.</param>
    /// <param name="messageId">The unique identifier of the request message.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the actor response handle.</returns>
    ValueTask<ActorResponseHandle> GetResponseAsync(ActorId actorId, string messageId, CancellationToken cancellationToken);
}
