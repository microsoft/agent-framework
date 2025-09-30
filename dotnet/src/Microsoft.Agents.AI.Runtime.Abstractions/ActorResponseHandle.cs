// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Represents a handle to an actor response, allowing retrieval of the response data and status updates.
/// </summary>
public abstract class ActorResponseHandle : IDisposable
{
    /// <summary>
    /// Attempts to get the response from the request if it is immediately available.
    /// </summary>
    /// <param name="response">When this method returns <see langword="true"/>, contains the actor response; otherwise, <see langword="null"/>.</param>
    /// <returns><see langword="true"/> if the response is immediately available; otherwise, <see langword="false"/>.</returns>
    /// <remarks>
    /// This method does not block and returns immediately. If the request is still pending or processing,
    /// this method returns <see langword="false"/>.
    /// Use <see cref="GetResponseAsync(CancellationToken)"/> to wait asynchronously for the response to become available.
    /// </remarks>
    public abstract bool TryGetResponse([NotNullWhen(true)] out ActorResponse? response);

    /// <summary>
    /// Gets the response from the completed request.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the request is finished.</returns>
    public abstract ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Cancels the request if it is still pending.
    /// </summary>
    /// <returns>A task representing the cancellation operation.</returns>
    public abstract ValueTask CancelAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Watches for status and data updates to the request.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of request updates.</returns>
    public abstract IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync(CancellationToken cancellationToken);

    /// <inheritdoc/>
    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Disposes of the resources used by the <see cref="ActorResponseHandle"/> class.
    /// </summary>
    /// <param name="disposing">A boolean indicating whether the method is being called from the <see cref="Dispose()"/> method.</param>
    protected virtual void Dispose(bool disposing) { }
}
