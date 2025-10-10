// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AsyncCoordinator
{
    private AsyncBarrier? _coordinationBarrier;

    /// <summary>
    /// Wait for the Coordination owner to mark the next coordination point, then continue execution.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result is <see langword="true"/>
    /// if the wait was completed; otherwise, for example, if the wait was cancelled, <see langword="false"/>.
    /// </returns>
    public async ValueTask<bool> WaitForCoordinationAsync(CancellationToken cancellationToken = default)
    {
        // There is a chance that we might get a stale barrier that is getting released if there is a
        // release happening concurrently with this call. This is by design, and should be considered
        // when using this class.
        AsyncBarrier actualBarrier = this._coordinationBarrier
                                  ?? Interlocked.CompareExchange(ref this._coordinationBarrier, new(), null)
                                  ?? this._coordinationBarrier!; // Re-read after setting

        return await actualBarrier.JoinAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Marks the coordination point and releases any waiting operations if a coordination barrier is present.
    /// </summary>
    /// <returns>true if a coordination barrier was released; otherwise, false.</returns>
    public bool MarkCoordinationPoint()
    {
        AsyncBarrier? maybeBarrier = Interlocked.Exchange(ref this._coordinationBarrier, null);
        return maybeBarrier?.ReleaseBarrier() ?? false;
    }
}
