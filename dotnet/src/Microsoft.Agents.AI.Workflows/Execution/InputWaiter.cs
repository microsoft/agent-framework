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

    /// <summary>
    /// Waits until input is signaled. This wait never expires; it completes only when
    /// <see cref="SignalInput"/> is called or <paramref name="cancellationToken"/> is cancelled.
    /// </summary>
    /// <param name="cancellationToken">A token to cancel the wait.</param>
    public Task WaitForInputAsync(CancellationToken cancellationToken = default) => this._inputSignal.WaitAsync(cancellationToken);

    /// <summary>
    /// Waits until input is signaled or <paramref name="timeout"/> expires.
    /// </summary>
    /// <param name="timeout">The maximum time to wait for input.</param>
    /// <param name="cancellationToken">A token to cancel the wait.</param>
    /// <returns>
    /// <see langword="true"/> if the wait was released by <see cref="SignalInput"/>;
    /// <see langword="false"/> if <paramref name="timeout"/> expired first.
    /// </returns>
    public async Task<bool> WaitForInputAsync(TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        return await this._inputSignal.WaitAsync(timeout, cancellationToken).ConfigureAwait(false);
    }
}
