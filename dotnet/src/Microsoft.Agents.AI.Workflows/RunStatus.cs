// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Specifies the current operational state of a workflow run.
/// </summary>
public enum RunStatus
{
    /// <summary>
    /// The run has not yet started. This only occurs when running in "lockstep" mode.
    /// </summary>
    NotStarted,

    /// <summary>
    /// The run has halted, has no outstanding requets, but has not received a <see cref="RequestHaltEvent"/>.
    /// </summary>
    Idle,

    /// <summary>
    /// The run has halted, and has at least one outstanding <see cref="ExternalRequest"/>.
    /// </summary>
    PendingRequests,

    /// <summary>
    /// The user has ended the run. No further events will be emitted, and no messages can be sent to it.
    /// </summary>
    Ended,

    /// <summary>
    /// The workflow is currently running, and may receive events or requests.
    /// </summary>
    Running
}
