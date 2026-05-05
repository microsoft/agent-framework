// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the status of a sub-task managed by the <see cref="SubAgentsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum SubTaskStatus
{
    /// <summary>
    /// The sub-task is currently running.
    /// </summary>
    Running,

    /// <summary>
    /// The sub-task completed successfully.
    /// </summary>
    Completed,

    /// <summary>
    /// The sub-task failed with an error.
    /// </summary>
    Failed,

    /// <summary>
    /// The sub-task's in-flight reference was lost (e.g., after a restart),
    /// and its final state cannot be determined.
    /// </summary>
    Lost,
}
