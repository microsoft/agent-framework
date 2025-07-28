// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Orchestration.Workflows.Core;

/// <summary>
/// Provides a base class implementing the <see cref="IAsyncDisposable"/> interface using
/// the virtual Dispose pattern.
/// </summary>
public class DisposableObject : IAsyncDisposable
{
    /// <summary>
    /// Implements invocation of the DisposeAsync method when the object is finalized to
    /// dispose unmanaged resources properly.
    /// </summary>
    ~DisposableObject()
    {
        // Finalizer calls DisposeAsync to ensure resources are released.
        // This is a safety net in case DisposeAsync was not called.
#pragma warning disable CA2012 // Use ValueTasks correctly: Uses OnCompleted to properly handle the ValueTask return.
        ValueTask disposeTask = this.DisposeAsync(false);
#pragma warning restore CA2012 // Use ValueTasks correctly

        if (!disposeTask.IsCompleted)
        {
            using (ManualResetEvent barrier = new(false))
            {
                disposeTask.GetAwaiter().OnCompleted(() => barrier.Set());

                // Wait for the DisposeAsync to complete.
                barrier.WaitOne(); // TODO: Timeout?
            }
        }

        Debug.Assert(
            disposeTask.IsCompleted,
            "DisposeAsync should have completed in order to pass to this line.");
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        disposeTask.GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    /// <inheritdoc/>
    protected virtual ValueTask DisposeAsync(bool disposing)
    {
        return CompletedValueTaskSource.Completed;
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        await this.DisposeAsync(true).ConfigureAwait(false);
        GC.SuppressFinalize(this);
    }
}
