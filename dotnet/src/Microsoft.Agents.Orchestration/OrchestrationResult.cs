// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Represents the result of an orchestration operation that yields a value of type <typeparamref name="TValue"/>.
/// This class encapsulates the asynchronous completion of an orchestration process.
/// </summary>
/// <typeparam name="TValue">The type of the value produced by the orchestration.</typeparam>
public sealed partial class OrchestrationResult<TValue> : IAsyncDisposable
{
    private readonly OrchestrationContext _context;
    private readonly CancellationTokenSource _cancelSource;
    private readonly TaskCompletionSource<TValue> _completion;
    private readonly ILogger _logger;
    private readonly IAsyncDisposable? _additionalDisposable;
    private bool _isDisposed;

    internal OrchestrationResult(OrchestrationContext context, TaskCompletionSource<TValue> completion, CancellationTokenSource orchestrationCancelSource, ILogger logger, IAsyncDisposable? additionalDisposable = null)
    {
        this._cancelSource = orchestrationCancelSource;
        this._context = context;
        this._completion = completion;
        this._logger = logger;
        this._additionalDisposable = additionalDisposable;
    }

    /// <summary>
    /// Releases all resources used by the <see cref="OrchestrationResult{TValue}"/> instance.
    /// </summary>
    public async ValueTask DisposeAsync()
    {
        if (!this._isDisposed)
        {
            this._isDisposed = true;

            this._cancelSource.Dispose();

            if (this._additionalDisposable is { } ad)
            {
                await ad.DisposeAsync().ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Gets the orchestration name associated with this orchestration result.
    /// </summary>
    public string Orchestration => this._context.Orchestration;

    /// <summary>
    /// Gets the topic identifier associated with this orchestration result.
    /// </summary>
    public TopicId Topic => this._context.Topic;

    /// <summary>
    /// Gets a task that represents the completion of the orchestration result.
    /// </summary>
    public Task<TValue> Task => this._completion.Task;

    /// <summary>
    /// Cancel the orchestration associated with this result.
    /// </summary>
    /// <exception cref="ObjectDisposedException">Thrown if this instance has been disposed.</exception>
    /// <remarks>
    /// Cancellation is not expected to immediately halt the orchestration.  Messages that
    /// are already in-flight may still be processed.
    /// </remarks>
    public void Cancel()
    {
#if NET
        ObjectDisposedException.ThrowIf(this._isDisposed, this);
#else
        if (this._isDisposed)
        {
            throw new ObjectDisposedException(this.GetType().Name);
        }
#endif

        this.LogOrchestrationResultCanceled(this.Orchestration, this.Topic);
        this._cancelSource.Cancel();
    }

    /// <summary>Enable directly awaiting an <see cref="OrchestrationResult{TValue}"/> by using <see cref="Task"/>'s awaiter.</summary>
    [EditorBrowsable(EditorBrowsableState.Never)]
    public TaskAwaiter<TValue> GetAwaiter() => this.Task.GetAwaiter();

    /// <summary>
    /// Logs <see cref="OrchestrationResult{TValue}"/> canceled the orchestration.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "CANCELED {Orchestration}: {Topic}")]
    private partial void LogOrchestrationResultCanceled(
        string orchestration,
        TopicId topic);
}
