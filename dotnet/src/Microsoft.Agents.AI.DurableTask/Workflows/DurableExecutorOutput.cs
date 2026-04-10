// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Output payload from executor execution, containing the result, state updates, and emitted events.
/// </summary>
internal sealed class DurableExecutorOutput
{
    /// <summary>
    /// Gets the executor result.
    /// </summary>
    public string? Result { get; init; }

    /// <summary>
    /// Gets the state updates (scope-prefixed key to value; null indicates deletion).
    /// </summary>
    public Dictionary<string, string?> StateUpdates { get; init; } = [];

    /// <summary>
    /// Gets the scope names that were cleared.
    /// </summary>
    public List<string> ClearedScopes { get; init; } = [];

    /// <summary>
    /// Gets the workflow events emitted during execution.
    /// </summary>
    public List<string> Events { get; init; } = [];

    /// <summary>
    /// Gets the typed messages sent to downstream executors.
    /// </summary>
    public List<TypedPayload> SentMessages { get; init; } = [];

    /// <summary>
    /// Gets a value indicating whether the executor requested a workflow halt.
    /// </summary>
    public bool HaltRequested { get; init; }
}
