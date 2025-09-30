// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AsyncBarrier
{
    private readonly TaskCompletionSource<object> _completionSource = new();

    public async ValueTask JoinAsync(CancellationToken cancellation = default)
    {
        using CancellationTokenRegistration registration = cancellation.Register(() => this.ReleaseBarrier());
        await this._completionSource.Task.ConfigureAwait(false);
    }

    public void ReleaseBarrier()
    {
        this._completionSource.TrySetResult(new());
    }
}
