// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the serializable state of sub-tasks managed by the <see cref="SubAgentsProvider"/>,
/// stored in the session's <see cref="AgentSessionStateBag"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class SubAgentState
{
    /// <summary>
    /// Gets or sets the next ID to assign to a new sub-task.
    /// </summary>
    [JsonPropertyName("nextTaskId")]
    public int NextTaskId { get; set; } = 1;

    /// <summary>
    /// Gets the list of sub-task metadata entries.
    /// </summary>
    [JsonPropertyName("tasks")]
    public List<SubTaskInfo> Tasks { get; set; } = [];
}
