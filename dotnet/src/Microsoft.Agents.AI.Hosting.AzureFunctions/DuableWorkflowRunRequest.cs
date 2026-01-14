// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Represents a request to run a workflow in the Duable system.
/// </summary>
public sealed class DuableWorkflowRunRequest
{
    /// <summary>
    /// Gets or sets the name of the workflow.
    /// </summary>
    [JsonPropertyName("workflowName")]
    public string WorkflowName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the input string to be processed or analyzed.
    /// </summary>
    [JsonPropertyName("input")]
    public string Input { get; set; } = string.Empty;
}
