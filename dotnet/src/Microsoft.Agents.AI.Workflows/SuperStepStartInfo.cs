// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Debug information about the SuperStep starting to run.
/// </summary>
public sealed class SuperStepStartInfo(HashSet<string>? sendingExecutors = null)
{
    /// <summary>
    /// The unique identifiers of <see cref="Executor"/> instances that sent messages during the previous SuperStep.
    /// </summary>
    public HashSet<string> SendingExecutors { get; } = sendingExecutors ?? [];

    /// <summary>
    /// Gets a value indicating whether there are any external messages queued during the previous SuperStep.
    /// </summary>
    public bool HasExternalMessages { get; init; }

    /// <summary>
    /// Gets the <see cref="CheckpointInfo"/> corresponding to the checkpoint created at the start of this SuperStep, if any.
    /// <see langword="null"/> if checkpointing was not enabled when the run was started.
    /// </summary>
    public CheckpointInfo? Checkpoint { get; init; }
}
