// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// The result of a <see cref="HostedWorkflowState"/> run or resume.
/// </summary>
public sealed class HostedWorkflowRunResult
{
    internal HostedWorkflowRunResult(string sessionId, IReadOnlyList<Workflows.WorkflowEvent> events, Workflows.CheckpointInfo? checkpoint)
    {
        this.SessionId = sessionId;
        this.Events = events;
        this.Checkpoint = checkpoint;
    }

    /// <summary>
    /// Gets the application-selected session id this run was executed under.
    /// </summary>
    public string SessionId { get; }

    /// <summary>
    /// Gets the workflow events emitted during this run.
    /// </summary>
    public IReadOnlyList<Workflows.WorkflowEvent> Events { get; }

    /// <summary>
    /// Gets the head checkpoint recorded for the session after this run, or <see langword="null"/> when
    /// checkpointing produced no checkpoint.
    /// </summary>
    public Workflows.CheckpointInfo? Checkpoint { get; }
}
