// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Debug information about the SuperStep that finished running.
/// </summary>
public sealed class SuperStepCompletionInfo(IEnumerable<string> activatedExecutors, IEnumerable<string>? instantiatedExecutors = null)
{
    /// <summary>
    /// The unique identifiers of <see cref="Executor"/> instances that processed messages during this SuperStep
    /// </summary>
    public HashSet<string> ActivatedExecutors { get; } = [.. Throw.IfNull(activatedExecutors)];

    /// <summary>
    /// The unique identifiers of <see cref="Executor"/> instances newly created during this SuperStep
    /// </summary>
    public HashSet<string> InstantiatedExecutors { get; } = [.. instantiatedExecutors ?? []];

    /// <summary>
    /// A flag indicating whether the managed state was written to during this SuperStep. If the run was started
    /// with checkpointing, any updated during the checkpointing process are also included.
    /// </summary>
    public bool StateUpdated { get; init; }

    /// <summary>
    /// A flag indicating whether there are messages pending delivery after this SuperStep.
    /// </summary>
    public bool HasPendingMessages { get; init; }

    /// <summary>
    /// A flag indicating whether there are requests pending delivery after this SuperStep.
    /// </summary>
    public bool HasPendingRequests { get; init; }

    /// <summary>
    /// Gets the <see cref="CheckpointInfo"/> corresponding to the checkpoint created at the end of this SuperStep.
    /// <see langword="null"/> if checkpointing was not enabled when the run was started.
    /// </summary>
    public CheckpointInfo? Checkpoint { get; init; }
}
