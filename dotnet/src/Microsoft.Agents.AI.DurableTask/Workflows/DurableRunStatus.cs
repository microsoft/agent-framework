// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents the execution status of a durable workflow run.
/// </summary>
public enum DurableRunStatus
{
    /// <summary>
    /// The workflow instance was not found.
    /// </summary>
    NotFound,

    /// <summary>
    /// The workflow is pending and has not started.
    /// </summary>
    Pending,

    /// <summary>
    /// The workflow is currently running.
    /// </summary>
    Running,

    /// <summary>
    /// The workflow completed successfully.
    /// </summary>
    Completed,

    /// <summary>
    /// The workflow failed with an error.
    /// </summary>
    Failed,

    /// <summary>
    /// The workflow was terminated.
    /// </summary>
    Terminated,

    /// <summary>
    /// The workflow is suspended.
    /// </summary>
    Suspended,

    /// <summary>
    /// The workflow status is unknown.
    /// </summary>
    Unknown
}
