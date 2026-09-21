// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Holds non-serializable runtime references for in-flight background tasks within a single parent session.
/// </summary>
/// <remarks>
/// Properties are marked with <see cref="JsonIgnoreAttribute"/> because <see cref="Task{TResult}"/>
/// and <see cref="AgentSession"/> are not JSON-serializable. After deserialization (e.g., after a restart),
/// a fresh empty instance is created and any previously-running tasks are marked as
/// <see cref="BackgroundTaskStatus.Lost"/> by <see cref="BackgroundAgentsProvider"/>.
/// </remarks>
internal sealed class BackgroundAgentRuntimeState
{
    /// <summary>
    /// Gets an object used to synchronize access to the runtime references held by this instance.
    /// </summary>
    /// <remarks>
    /// Background task registration happens on the agent's tool-invocation path, while
    /// <see cref="BackgroundAgentsProvider.ReleaseSessionAsync"/> may be called concurrently by a host.
    /// All mutations of the dictionaries below, and of <see cref="IsReleased"/>, must be performed under this lock
    /// so that a task can never be registered into an already-released runtime.
    /// </remarks>
    [JsonIgnore]
    public object SyncRoot { get; } = new();

    /// <summary>
    /// Gets the mapping of task IDs to their in-flight <see cref="Task{AgentResponse}"/> instances.
    /// </summary>
    [JsonIgnore]
    public Dictionary<int, Task<AgentResponse>> InFlightTasks { get; } = [];

    /// <summary>
    /// Gets the mapping of task IDs to their background agent <see cref="AgentSession"/> instances,
    /// needed for <c>ContinueTask</c>.
    /// </summary>
    [JsonIgnore]
    public Dictionary<int, AgentSession> BackgroundTaskSessions { get; } = [];

    /// <summary>
    /// Gets the mapping of task IDs to the <see cref="CancellationTokenSource"/> controlling their run.
    /// </summary>
    /// <remarks>
    /// A source is created when a task is started or continued, and is disposed and removed when the task is
    /// finalized, cleared, or when the session is released via <see cref="BackgroundAgentsProvider.ReleaseSessionAsync"/>.
    /// </remarks>
    [JsonIgnore]
    public Dictionary<int, CancellationTokenSource> TaskCancellations { get; } = [];

    /// <summary>
    /// Gets or sets a value indicating whether this runtime has been released via
    /// <see cref="BackgroundAgentsProvider.ReleaseSessionAsync"/>.
    /// </summary>
    /// <remarks>
    /// Once released, all in-flight tasks have been cancelled and awaited, and the runtime references have been
    /// dropped. Tools that would start new background work refuse to run against a released runtime.
    /// </remarks>
    [JsonIgnore]
    public bool IsReleased { get; set; }

    /// <summary>
    /// Gets or sets the completion signalled once the release of this runtime has finished all of its cleanup.
    /// </summary>
    /// <remarks>
    /// Set under <see cref="SyncRoot"/> by the caller that first releases the runtime, and completed once that
    /// caller has finished waiting for the in-flight tasks and has dropped the runtime references. Callers that
    /// arrive while a release is already in progress await this instead of returning early, so that a completed
    /// <see cref="BackgroundAgentsProvider.ReleaseSessionAsync"/> always means the cleanup is done. It is completed
    /// successfully even when the releasing caller fails, because a waiter should observe that cleanup finished
    /// rather than inherit another caller's failure.
    /// </remarks>
    [JsonIgnore]
    public TaskCompletionSource<bool>? ReleaseCompletion { get; set; }
}
