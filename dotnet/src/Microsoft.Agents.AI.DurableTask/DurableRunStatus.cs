// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the execution status of a durable workflow run.
/// </summary>
public enum DurableRunStatus
{
    /// <summary>
    /// The orchestration instance was not found.
    /// </summary>
    NotFound,

    /// <summary>
    /// The orchestration is pending and has not started.
    /// </summary>
    Pending,

    /// <summary>
    /// The orchestration is currently running.
    /// </summary>
    Running,

    /// <summary>
    /// The orchestration completed successfully.
    /// </summary>
    Completed,

    /// <summary>
    /// The orchestration failed with an error.
    /// </summary>
    Failed,

    /// <summary>
    /// The orchestration was terminated.
    /// </summary>
    Terminated,

    /// <summary>
    /// The orchestration is suspended.
    /// </summary>
    Suspended,

    /// <summary>
    /// The orchestration status is unknown.
    /// </summary>
    Unknown
}
