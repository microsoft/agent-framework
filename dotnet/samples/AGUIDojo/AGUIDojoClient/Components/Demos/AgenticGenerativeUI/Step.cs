// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoClient.Components.Demos.AgenticGenerativeUI;

/// <summary>
/// Represents a single step in a plan.
/// </summary>
public sealed class Step
{
    /// <summary>
    /// The description of the step.
    /// </summary>
    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    /// <summary>
    /// The status of the step (pending or completed).
    /// </summary>
    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    /// <summary>
    /// Gets whether this step is completed.
    /// </summary>
    [JsonIgnore]
    public bool IsCompleted => string.Equals(this.Status, "completed", StringComparison.OrdinalIgnoreCase);
}
