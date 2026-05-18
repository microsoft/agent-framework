// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the metadata and result of a background task managed by the <see cref="BackgroundAgentsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundTaskInfo
{
    /// <summary>
    /// Gets or sets the unique identifier for this background task.
    /// </summary>
    [JsonPropertyName("id")]
    public int Id { get; set; }

    /// <summary>
    /// Gets or sets the name of the agent that is executing this background task.
    /// </summary>
    [JsonPropertyName("agentName")]
    public string AgentName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets a description of what this background task is doing.
    /// </summary>
    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the current status of this background task.
    /// </summary>
    [JsonPropertyName("status")]
    public BackgroundTaskStatus Status { get; set; }

    /// <summary>
    /// Gets or sets the text result of the background task, populated when the task completes successfully.
    /// </summary>
    [JsonPropertyName("resultText")]
    public string? ResultText { get; set; }

    /// <summary>
    /// Gets or sets the error message if the background task failed.
    /// </summary>
    [JsonPropertyName("errorText")]
    public string? ErrorText { get; set; }
}
