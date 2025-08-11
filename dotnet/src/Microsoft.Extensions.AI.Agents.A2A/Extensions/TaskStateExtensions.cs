// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.Extensions;

/// <summary>
/// Helpers for <see cref="TaskState"/>.
/// </summary>
public static class TaskStateExtensions
{
    /// <summary>
    /// Determines whether the specified <see cref="AgentTaskStatus"/> is in an active state.
    /// </summary>
    public static bool IsActive(this AgentTaskStatus status)
        => status.State.IsActive();

    /// <summary>
    /// Determines whether the specified <see cref="AgentTaskStatus"/> is in a completed state.
    /// </summary>
    public static bool IsCompleted(this AgentTaskStatus status)
        => status.State.IsCompleted();

    /// <summary>
    /// Determines whether the specified <see cref="TaskState"/> is in an active state.
    /// </summary>
    public static bool IsActive(this TaskState state)
    => state is TaskState.Working
             or TaskState.Submitted;

    /// <summary>
    /// Determines whether the specified <see cref="TaskState"/> is in a completed state.
    /// </summary>
    public static bool IsCompleted(this TaskState state)
        => state is TaskState.Completed
                 or TaskState.Failed
                 or TaskState.Canceled
                 or TaskState.Rejected;
}
