// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.ExceptionServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Coordinates invocation admission and shutdown across cached and provider-backed clients.
/// </summary>
internal sealed class McpClientLifetime : IDisposable
{
    private readonly AsyncLocal<ProviderInvocationContext?> _providerInvocationContext = new();
    private TaskCompletionSource<bool>? _providerInvocationsDrained;
    private int _activeProviderInvocations;

    public SemaphoreSlim SyncLock { get; } = new(1, 1);

    public bool IsDisposing { get; private set; }

    public async Task<T> InvokeProviderAsync<T>(Func<Task<T>> invocation, CancellationToken cancellationToken)
    {
        TaskCompletionSource<bool> invocationCompleted = new(TaskCreationOptions.RunContinuationsAsynchronously);
        await this.SyncLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            this.ThrowIfDisposing();
            if (this._activeProviderInvocations++ == 0)
            {
                this._providerInvocationsDrained = new(TaskCreationOptions.RunContinuationsAsynchronously);
            }
        }
        finally
        {
            this.SyncLock.Release();
        }

        ProviderInvocationContext? previousInvocation = this._providerInvocationContext.Value;
        this._providerInvocationContext.Value = new(invocationCompleted.Task, previousInvocation);
        try
        {
            return await invocation().ConfigureAwait(false);
        }
        finally
        {
            await this.SyncLock.WaitAsync(CancellationToken.None).ConfigureAwait(false);
            try
            {
                if (--this._activeProviderInvocations == 0)
                {
                    this._providerInvocationsDrained!.SetResult(true);
                }
            }
            finally
            {
                invocationCompleted.SetResult(true);
                this._providerInvocationContext.Value = previousInvocation;
                this.SyncLock.Release();
            }
        }
    }

    public void ThrowIfProviderInvocationActive()
    {
        for (ProviderInvocationContext? context = this._providerInvocationContext.Value; context is not null; context = context.Parent)
        {
            if (!context.Completion.IsCompleted)
            {
                throw new InvalidOperationException("Cannot dispose the MCP handler from an active provider-backed invocation.");
            }
        }
    }

    // Called with SyncLock held so shutdown and invocation admission are atomic.
    public Task BeginDisposalAsync()
    {
        this.ThrowIfDisposing();
        this.IsDisposing = true;
        return this._providerInvocationsDrained?.Task ?? Task.CompletedTask;
    }

    public void Dispose() => this.SyncLock.Dispose();

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
        Justification = "The helper is not available on .NET Framework or .NET Standard 2.0.")]
    public void ThrowIfDisposing()
    {
        if (this.IsDisposing)
        {
            throw new ObjectDisposedException(nameof(DefaultMcpToolHandler));
        }
    }

    internal static async Task DrainCleanupAsync(IEnumerable<Task> cleanupTasks, IEnumerable<Task> completionTasks)
    {
        Exception? cleanupException = null;
        try
        {
            await Task.WhenAll(cleanupTasks).ConfigureAwait(false);
        }
        catch (Exception exception) when (!IsFatalException(exception))
        {
            cleanupException = exception;
        }

        await Task.WhenAll(completionTasks).ConfigureAwait(false);

        if (cleanupException is not null)
        {
            ExceptionDispatchInfo.Capture(cleanupException).Throw();
        }
    }

    internal static bool IsFatalException(Exception exception) =>
        exception is OutOfMemoryException and not InsufficientMemoryException
        or StackOverflowException
        or AccessViolationException
        or AppDomainUnloadedException
        or BadImageFormatException
        or CannotUnloadAppDomainException
        or InvalidProgramException
        or ThreadAbortException;

    private sealed class ProviderInvocationContext(Task completion, ProviderInvocationContext? parent)
    {
        public Task Completion { get; } = completion;
        public ProviderInvocationContext? Parent { get; } = parent;
    }
}
