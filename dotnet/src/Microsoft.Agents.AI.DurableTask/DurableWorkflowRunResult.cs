// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the result of a durable workflow orchestration execution.
/// </summary>
public sealed class DurableWorkflowRunResult
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowRunResult"/> class.
    /// </summary>
    /// <param name="workflowName">The name of the workflow that was executed.</param>
    /// <param name="output">The output from the workflow execution.</param>
    public DurableWorkflowRunResult(string workflowName, string output)
    {
        this.WorkflowName = workflowName;
        this.Output = output;
    }

    /// <summary>
    /// Gets the name of the workflow that was executed.
    /// </summary>
    [JsonPropertyName("workflowName")]
    public string WorkflowName { get; }

    /// <summary>
    /// Gets the output from the workflow execution.
    /// </summary>
    [JsonPropertyName("output")]
    public string Output { get; }
}
