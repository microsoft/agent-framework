// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a workflow run that can be awaited for completion.
/// </summary>
/// <remarks>
/// <para>
/// This interface extends <see cref="IWorkflowRun"/> to provide methods for waiting
/// until the workflow execution completes. Not all workflow runners support this capability.
/// </para>
/// <para>
/// Use pattern matching to check if a workflow run supports awaiting:
/// <code>
/// IWorkflowRun run = await client.RunAsync(workflow, input);
/// if (run is IAwaitableWorkflowRun awaitableRun)
/// {
///     string? result = await awaitableRun.WaitForCompletionAsync&lt;string&gt;();
/// }
/// </code>
/// </para>
/// </remarks>
public interface IAwaitableWorkflowRun : IWorkflowRun
{
    /// <summary>
    /// Waits for the workflow to complete and returns the result.
    /// </summary>
    /// <typeparam name="TResult">The expected result type.</typeparam>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The result of the workflow execution.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the workflow failed or was terminated.</exception>
    ValueTask<TResult?> WaitForCompletionAsync<TResult>(CancellationToken cancellationToken = default);
}
