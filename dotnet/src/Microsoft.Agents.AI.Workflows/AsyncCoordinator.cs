// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AsyncCoordinator
{
    private AsyncBarrier? _coordinationBarrier;

    public async ValueTask WaitForCoordinationAsync(CancellationToken cancellation = default)
    {
        AsyncBarrier newBarrier = new();
        AsyncBarrier? actualBarrier = Interlocked.CompareExchange(ref this._coordinationBarrier, newBarrier, null);
        actualBarrier ??= newBarrier;

        await actualBarrier.JoinAsync(cancellation).ConfigureAwait(false);
    }

    public void MarkCoordinationPoint()
    {
        AsyncBarrier? maybeBarrier = Interlocked.Exchange(ref this._coordinationBarrier, null);
        maybeBarrier?.ReleaseBarrier();
    }
}
