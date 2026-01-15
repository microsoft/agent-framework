// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Represents a request to run a durable workflow.
/// </summary>
internal sealed class DuableWorkflowRunRequest
{
    /// <summary>
    /// Gets or sets the name of the workflow to execute.
    /// </summary>
    [JsonPropertyName("workflowName")]
    public string WorkflowName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the input for the workflow.
    /// </summary>
    [JsonPropertyName("input")]
    public string Input { get; set; } = string.Empty;
}
