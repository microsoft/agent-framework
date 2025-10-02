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
    /// <param name="cancellation">A cancellation token that can be used to cancel the wait.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result is <see langword="true"/>
    /// if the wait was completed; otherwise, for example, if the wait was cancelled, <see langword="false"/>.
    /// </returns>
    public async ValueTask<bool> WaitForCoordinationAsync(CancellationToken cancellation = default)
    {
        // Init, but do not wait into a new Barrier
        AsyncBarrier newBarrier = new();

        // Check if there is not already a barrier; if there is, use that one instead
        AsyncBarrier? actualBarrier = Interlocked.CompareExchange(ref this._coordinationBarrier, newBarrier, null);

        // If actualBarrier was not null, there exists a barrier; use that one. If it is null, use the new one we created.
        actualBarrier ??= newBarrier;

        return await actualBarrier.JoinAsync(cancellation).ConfigureAwait(false);
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
