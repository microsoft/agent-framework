// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides a registry for storing and retrieving executor bindings independently from workflows.
/// </summary>
internal sealed class ExecutorRegistry
{
    private readonly Dictionary<string, ExecutorRegistration> _executors = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Gets the number of registered executors.
    /// </summary>
    public int Count => this._executors.Count;

    /// <summary>
    /// Attempts to get an executor registration by name.
    /// </summary>
    /// <param name="executorName">The executor name to look up.</param>
    /// <param name="registration">When this method returns, contains the registration if found; otherwise, null.</param>
    /// <returns><see langword="true"/> if the executor was found; otherwise, <see langword="false"/>.</returns>
    public bool TryGetExecutor(string executorName, out ExecutorRegistration? registration)
    {
        return this._executors.TryGetValue(executorName, out registration);
    }

    /// <summary>
    /// Registers an executor binding from a workflow.
    /// </summary>
    /// <param name="executorName">The executor name (without GUID suffix).</param>
    /// <param name="executorId">The full executor ID (may include GUID suffix).</param>
    /// <param name="workflow">The workflow containing the executor.</param>
    internal void Register(string executorName, string executorId, Workflow workflow)
    {
        ArgumentException.ThrowIfNullOrEmpty(executorName);
        ArgumentException.ThrowIfNullOrEmpty(executorId);
        ArgumentNullException.ThrowIfNull(workflow);

        this._executors.TryAdd(executorName, new ExecutorRegistration(executorId, workflow));
    }
}

/// <summary>
/// Represents a registered executor with its associated workflow.
/// </summary>
/// <param name="ExecutorId">The full executor ID (may include GUID suffix).</param>
/// <param name="Workflow">The workflow containing the executor.</param>
internal sealed record ExecutorRegistration(string ExecutorId, Workflow Workflow)
{
    /// <summary>
    /// Creates an instance of the executor.
    /// </summary>
    /// <param name="runId">A unique identifier for the run context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The created executor instance.</returns>
    public ValueTask<Executor> CreateExecutorInstanceAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this.Workflow.CreateExecutorInstanceAsync(this.ExecutorId, runId, cancellationToken);
    }
}
