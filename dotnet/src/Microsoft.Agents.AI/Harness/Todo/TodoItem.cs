// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a single todo item managed by the <see cref="TodoProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TodoItem
{
    /// <summary>
    /// Gets or sets the unique identifier for this todo item.
    /// </summary>
    [JsonPropertyName("id")]
    public int Id { get; set; }

    /// <summary>
    /// Gets or sets the title of this todo item.
    /// </summary>
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets an optional description providing additional details about this todo item.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether this todo item has been completed.
    /// </summary>
    [JsonPropertyName("isComplete")]
    public bool IsComplete { get; set; }
}
