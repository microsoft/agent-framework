// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Applies one shared timeout across the steps of an operation while preserving caller cancellation.
/// </summary>
internal sealed class MultiStepOperationTimeout : IDisposable
{
    private readonly CancellationToken _callerToken;
    private readonly CancellationTokenSource _timeoutSource;

    /// <summary>
    /// Initializes a timeout linked to the caller's cancellation token.
    /// </summary>
    /// <param name="timeout">The maximum time allowed for the operation.</param>
    /// <param name="cancellationToken">The caller's cancellation token.</param>
    public MultiStepOperationTimeout(TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        this._callerToken = cancellationToken;
        this._timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        this._timeoutSource.CancelAfter(timeout);
        this.Token = this._timeoutSource.Token;
    }

    /// <summary>
    /// Gets a token cancelled by either the caller or the timeout.
    /// </summary>
    public CancellationToken Token { get; }

    /// <summary>
    /// Runs one synchronous step with the shared timeout token.
    /// </summary>
    /// <typeparam name="T">The type returned by the operation.</typeparam>
    /// <param name="step">The step to run.</param>
    /// <returns>The step result.</returns>
    /// <exception cref="OperationCanceledException">The caller cancelled the operation.</exception>
    /// <exception cref="TimeoutException">The operation exceeded its time limit.</exception>
    public T RunStep<T>(Func<CancellationToken, T> step)
    {
        if (step is null)
        {
            throw new ArgumentNullException(nameof(step));
        }

        this.ThrowIfCancellationRequested();

        try
        {
            T result = step(this.Token);
            this.ThrowIfCancellationRequested();
            return result;
        }
        catch (OperationCanceledException) when (this.Token.IsCancellationRequested)
        {
            this.ThrowIfCancellationRequested();
            throw;
        }
    }

    /// <summary>
    /// Runs one asynchronous step with the shared timeout token and stops waiting when the timeout expires.
    /// </summary>
    /// <typeparam name="T">The type returned by the operation.</typeparam>
    /// <param name="step">The step to run.</param>
    /// <returns>The step result.</returns>
    /// <exception cref="OperationCanceledException">The caller cancelled the operation.</exception>
    /// <exception cref="TimeoutException">The operation exceeded its time limit.</exception>
    public async Task<T> RunStepAsync<T>(Func<CancellationToken, Task<T>> step)
    {
        if (step is null)
        {
            throw new ArgumentNullException(nameof(step));
        }

        // Do not start another step after the caller has cancelled or the shared timeout has expired.
        this.ThrowIfCancellationRequested();

        Task<T> stepTask;
        try
        {
            stepTask = step(this.Token);
        }
        catch (OperationCanceledException) when (this.Token.IsCancellationRequested)
        {
            // The step may observe the linked token before returning its task. Convert that
            // cancellation now so caller cancellation still takes priority over timeout expiry.
            this.ThrowIfCancellationRequested();
            throw;
        }

        // A step is allowed to ignore the supplied token. Race it against an explicit cancellation
        // signal so this method stops waiting when the shared timeout expires.
        var cancellationSignal = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using CancellationTokenRegistration registration = this.Token.Register(
            static state => ((TaskCompletionSource<bool>)state!).TrySetResult(true),
            cancellationSignal);
        _ = await Task.WhenAny(stepTask, cancellationSignal.Task).ConfigureAwait(false);

        if (!stepTask.IsCompleted)
        {
            // The timed-out step may continue running. Observe any later fault before reporting the
            // cancellation or timeout so it cannot become an unobserved task exception.
            ObserveFault(stepTask);
            this.ThrowIfCancellationRequested();
        }

        try
        {
            T result = await stepTask.ConfigureAwait(false);

            // The step and timeout can finish together. Check the shared token before returning a
            // result so an expired multi-step operation is not reported as successful.
            this.ThrowIfCancellationRequested();
            return result;
        }
        catch (OperationCanceledException) when (this.Token.IsCancellationRequested)
        {
            // Distinguish caller cancellation from expiry of the shared timer.
            this.ThrowIfCancellationRequested();
            throw;
        }
    }

    /// <summary>
    /// Throws when the caller cancelled the operation or its timeout expired.
    /// </summary>
    /// <exception cref="OperationCanceledException">The caller cancelled the operation.</exception>
    /// <exception cref="TimeoutException">The operation exceeded its time limit.</exception>
    public void ThrowIfCancellationRequested()
    {
        this._callerToken.ThrowIfCancellationRequested();
        if (this.Token.IsCancellationRequested)
        {
            throw new TimeoutException("The operation exceeded its time limit.");
        }
    }

    /// <inheritdoc />
    public void Dispose() => this._timeoutSource.Dispose();

    private static void ObserveFault(Task task) =>
        _ = task.ContinueWith(
            static completedTask => _ = completedTask.Exception,
            CancellationToken.None,
            TaskContinuationOptions.ExecuteSynchronously | TaskContinuationOptions.OnlyOnFaulted,
            TaskScheduler.Default);
}
