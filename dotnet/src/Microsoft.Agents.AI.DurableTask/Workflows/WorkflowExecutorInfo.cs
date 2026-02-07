// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents an executor in the workflow with its metadata.
/// </summary>
/// <param name="ExecutorId">The unique identifier of the executor.</param>
/// <param name="IsAgenticExecutor">Indicates whether this executor is an agentic executor.</param>
/// <param name="RequestPort">The request port if this executor is a request port executor; otherwise, null.</param>
/// <param name="SubWorkflow">The sub-workflow if this executor is a sub-workflow executor; otherwise, null.</param>
internal sealed record WorkflowExecutorInfo(
    string ExecutorId,
    bool IsAgenticExecutor,
    RequestPort? RequestPort = null,
    Workflow? SubWorkflow = null)
{
    /// <summary>
    /// Gets a value indicating whether this executor is a request port executor (human-in-the-loop).
    /// </summary>
    public bool IsRequestPortExecutor => this.RequestPort is not null;

    /// <summary>
    /// Gets a value indicating whether this executor is a sub-workflow executor.
    /// </summary>
    public bool IsSubworkflowExecutor => this.SubWorkflow is not null;
}
