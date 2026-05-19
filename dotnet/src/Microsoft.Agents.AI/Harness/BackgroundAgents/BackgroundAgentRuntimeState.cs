// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
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
}
