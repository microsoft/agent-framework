// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the state of the todo list managed by the <see cref="TodoProvider"/>,
/// stored in the session's <see cref="AgentSessionStateBag"/>.
/// </summary>
internal sealed class TodoState
{
    /// <summary>
    /// Gets the list of todo items.
    /// </summary>
    [JsonPropertyName("items")]
    public List<TodoItem> Items { get; set; } = [];

    /// <summary>
    /// Gets or sets the next ID to assign to a new todo item.
    /// </summary>
    [JsonPropertyName("nextId")]
    public int NextId { get; set; } = 1;
}
