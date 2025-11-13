// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoClient.Components.Demos.HumanInTheLoop;

/// <summary>
/// Represents a plan with multiple steps.
/// </summary>
public sealed class Plan
{
    /// <summary>
    /// The list of steps in the plan.
    /// </summary>
    [JsonPropertyName("steps")]
    public List<Step> Steps { get; set; } = [];

    /// <summary>
    /// Gets the count of completed steps.
    /// </summary>
    [JsonIgnore]
    public int CompletedCount => this.Steps.Count(s => s.IsCompleted);

    /// <summary>
    /// Gets the total number of steps.
    /// </summary>
    [JsonIgnore]
    public int TotalCount => this.Steps.Count;

    /// <summary>
    /// Gets whether all steps are completed.
    /// </summary>
    [JsonIgnore]
    public bool IsComplete => this.Steps.Count > 0 && this.Steps.All(s => s.IsCompleted);
}
