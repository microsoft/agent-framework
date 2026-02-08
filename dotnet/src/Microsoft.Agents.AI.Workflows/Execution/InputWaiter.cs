// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class InputWaiter : IDisposable
{
    private readonly SemaphoreSlim _inputSignal = new(initialCount: 0, 1);

    public void Dispose()
    {
        this._inputSignal.Dispose();
    }

    /// <summary>
    /// Signals that new input has been provided and the waiter should continue processing.
    /// Called by AsyncRunHandle when the user enqueues a message or response.
    /// </summary>
    public void SignalInput()
    {
        // Release the run loop to process more work
        // Only release if not already signaled (binary semaphore behavior)
        try
        {
            this._inputSignal.Release();
        }
        catch (SemaphoreFullException)
        {
            // Swallow for now
        }
    }

    public Task WaitForInputAsync(CancellationToken cancellationToken = default) => this.WaitForInputAsync(null, cancellationToken);

    public async Task WaitForInputAsync(TimeSpan? timeout = null, CancellationToken cancellationToken = default)
    {
        await this._inputSignal.WaitAsync(timeout ?? TimeSpan.FromMilliseconds(-1), cancellationToken).ConfigureAwait(false);
    }
}
