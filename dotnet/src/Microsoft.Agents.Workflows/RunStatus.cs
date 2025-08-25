// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Specifies the current operational state of a workflow run.
/// </summary>
public enum RunStatus
{
    /// <summary>
    /// The run has has halted without no outstanding requests, but has not a <see cref="WorkflowCompletedEvent"/>.
    /// </summary>
    Idle,

    /// <summary>
    /// The run has halted, and has at least one outstanding <see cref="ExternalRequest"/>.
    /// </summary>
    PendingRequests,

    /// <summary>
    /// The run has halted after receiving a <see cref="WorkflowCompletedEvent"/>.
    /// </summary>
    Completed,

    /// <summary>
    /// The workflow is currently running, and may receive events or requests.
    /// </summary>
    Running
}
