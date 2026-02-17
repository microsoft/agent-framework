// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Output payload from activity execution, containing the result, state updates, and emitted events.
/// </summary>
internal sealed class DurableActivityOutput
{
    /// <summary>
    /// Gets or sets the executor result.
    /// </summary>
    public string? Result { get; set; }

    /// <summary>
    /// Gets or sets the state updates (scope-prefixed key to value; null indicates deletion).
    /// </summary>
    public Dictionary<string, string?> StateUpdates { get; set; } = [];

    /// <summary>
    /// Gets or sets the scope names that were cleared.
    /// </summary>
    public List<string> ClearedScopes { get; set; } = [];

    /// <summary>
    /// Gets or sets the workflow events emitted during execution.
    /// </summary>
    public List<string> Events { get; set; } = [];

    /// <summary>
    /// Gets or sets the typed messages sent to downstream executors.
    /// </summary>
    public List<TypedPayload> SentMessages { get; set; } = [];

    /// <summary>
    /// Gets or sets a value indicating whether the executor requested a workflow halt.
    /// </summary>
    public bool HaltRequested { get; set; }
}
