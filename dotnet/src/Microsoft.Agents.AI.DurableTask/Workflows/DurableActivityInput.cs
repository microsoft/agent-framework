// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Input payload for activity execution, containing the input and other metadata.
/// </summary>
internal sealed class DurableActivityInput
{
    /// <summary>
    /// Gets or sets the serialized executor input.
    /// </summary>
    public string? Input { get; set; }

    /// <summary>
    /// Gets or sets the assembly-qualified type name of the input, used for proper deserialization.
    /// </summary>
    public string? InputTypeName { get; set; }

    /// <summary>
    /// Gets or sets the shared state dictionary (scope-prefixed key -> serialized value).
    /// </summary>
    public Dictionary<string, string> State { get; set; } = [];
}
