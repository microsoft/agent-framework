// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a subworkflow encounters a warning-confition.
/// sub-workflow.
/// </summary>
/// <param name="message">The warning message.</param>
/// <param name="subWorkflowId">The unique identifier of the sub-workflow that triggered the warning. Cannot be null or empty.</param>
public sealed class SubworkflowWarningEvent(string message, string subWorkflowId) : WorkflowWarningEvent(message)
{
    /// <summary>
    /// The unique identifier of the sub-workflow that triggered the warning.
    /// </summary>
    public string SubWorkflowId { get; } = subWorkflowId;
}
