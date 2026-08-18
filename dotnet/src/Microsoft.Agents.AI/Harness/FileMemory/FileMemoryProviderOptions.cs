// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="FileMemoryProvider"/>.
/// </summary>
public sealed class FileMemoryProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent for using the file memory tools.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider uses built-in instructions
    /// that guide the agent on how to use file-based memory effectively.
    /// </value>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to skip the check that a store's reported
    /// <see cref="FileSearchMatch.LineNumber"/> values address the same lines the line editor acts on.
    /// </summary>
    /// <remarks>
    /// The check only runs for a store that overrides <see cref="AgentFileStore.SearchAsync"/> without
    /// declaring <see cref="AgentFileStore.ReportsAlignedLineNumbers"/>, and costs one extra read per
    /// <em>matched</em> file. Turn it off only when the store's alignment is established some other
    /// way: without it, a mis-numbered grep result reaches the model and an edit can land on the wrong
    /// line silently. Prefer setting <see cref="AgentFileStore.ReportsAlignedLineNumbers"/> on the
    /// store, which opts out one store rather than every store this provider is given.
    /// </remarks>
    public bool DisableSearchAlignmentCheck { get; set; }
}
