// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the input for creating a new todo item via the <see cref="TodoProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class TodoItemInput
{
    /// <summary>
    /// Gets or sets the title of the todo item to create.
    /// </summary>
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets an optional description providing additional details about the todo item.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }
}
