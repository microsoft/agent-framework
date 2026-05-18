// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the serializable state of background tasks managed by the <see cref="BackgroundAgentsProvider"/>,
/// stored in the session's <see cref="AgentSessionStateBag"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class BackgroundAgentState
{
    /// <summary>
    /// Gets or sets the next ID to assign to a new background task.
    /// </summary>
    [JsonPropertyName("nextTaskId")]
    public int NextTaskId { get; set; } = 1;

    /// <summary>
    /// Gets the list of background task metadata entries.
    /// </summary>
    [JsonPropertyName("tasks")]
    public List<BackgroundTaskInfo> Tasks { get; set; } = [];
}
