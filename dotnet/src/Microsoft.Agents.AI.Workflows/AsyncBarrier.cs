// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AsyncBarrier()
{
    private readonly InitLocked<TaskCompletionSource<object>> _completionSource = new();

    public async ValueTask<bool> JoinAsync(CancellationToken cancellation = default)
    {
        this._completionSource.Init(() => new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously));
        TaskCompletionSource<object> completionSource = this._completionSource.Get()!;

        // Create a new completion source to track cancellation, because cancelling a single waiter's join
        // should not cancel the entire barrier.
        TaskCompletionSource<object> cancellationSource = new();

        using CancellationTokenRegistration registration = cancellation.Register(() => cancellationSource.SetResult(new()));

        await Task.WhenAny(completionSource.Task, cancellationSource.Task).ConfigureAwait(false);
        return !cancellation.IsCancellationRequested;
    }

    public bool ReleaseBarrier()
    {
        // If there is no completion source, then there are no waiters.
        return this._completionSource.Get()?.TrySetResult(new()) ?? false;
    }
}
