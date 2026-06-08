// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the status of a background task managed by the <see cref="BackgroundAgentsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum BackgroundTaskStatus
{
    /// <summary>
    /// The background task is currently running.
    /// </summary>
    Running,

    /// <summary>
    /// The background task completed successfully.
    /// </summary>
    Completed,

    /// <summary>
    /// The background task failed with an error.
    /// </summary>
    Failed,

    /// <summary>
    /// The background task's in-flight reference was lost (e.g., after a restart),
    /// and its final state cannot be determined.
    /// </summary>
    Lost,
}
