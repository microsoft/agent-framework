// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.InProc;

internal class DataWaiter : IDisposable
{
    private readonly ManualResetEvent _dataAvailable = new(false);
    private readonly InitLocked<Task> _waitOnDataTask = new();
    private readonly CancellationTokenSource _cancellationTokenSource = new();

    public void Signal()
    {
        this._dataAvailable.Set();
    }

    public async ValueTask JoinWaitForDataAsync(CancellationToken cancellation = default)
    {
        Task? waitTask = this._waitOnDataTask.Get();
        if (waitTask != null)
        {
            await waitTask.ConfigureAwait(false);
        }
    }

    public void Reset()
    {
        this._dataAvailable.Reset();
        this._waitOnDataTask.Init(() => Task.Run(() => this._dataAvailable.WaitOne(), this._cancellationTokenSource.Token));
    }

    public void Dispose()
    {
        this._cancellationTokenSource.Cancel();

        this._cancellationTokenSource.Dispose();
        this._dataAvailable.Dispose();
    }
}
