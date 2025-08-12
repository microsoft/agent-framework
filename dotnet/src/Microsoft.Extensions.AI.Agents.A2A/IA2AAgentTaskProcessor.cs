// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Is a more complicated form of A2A communication where the agent can process AgentTasks.
/// AgentTask is a representation of stateful potentially long-running conversation between user (client or another agent) and this agent.
/// See details at <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/life-of-a-task.md">A2A docs</see>
/// </summary>
public interface IA2AAgentTaskProcessor
{
    /// <summary>
    /// Creates a new agent task, representing a stateful, potentially long-running conversation between a user and the agent.
    /// </summary>
    /// <param name="task">The <see cref="AgentTask"/> to be created.</param>
    /// <param name="token">A <see cref="CancellationToken"/> to observe while waiting for the task to complete.</param>
    /// <returns>A <see cref="Task"/> that represents the asynchronous operation.</returns>
    Task CreateTaskAsync(AgentTask task, CancellationToken token = default);

    /// <summary>
    /// Cancels an existing agent task, terminating the associated conversation or operation.
    /// </summary>
    /// <param name="task">The <see cref="AgentTask"/> to be cancelled.</param>
    /// <param name="token">A <see cref="CancellationToken"/> to observe while waiting for the cancellation to complete.</param>
    /// <returns>A <see cref="Task"/> that represents the asynchronous cancellation operation.</returns>
    Task CancelTaskAsync(AgentTask task, CancellationToken token = default);

    /// <summary>
    /// Updates an existing agent task, modifying its state or associated data as needed.
    /// </summary>
    /// <param name="task">The <see cref="AgentTask"/> to be updated.</param>
    /// <param name="token">A <see cref="CancellationToken"/> to observe while waiting for the update to complete.</param>
    /// <returns>A <see cref="Task"/> that represents the asynchronous update operation.</returns>
    Task UpdateTaskAsync(AgentTask task, CancellationToken token = default);

    /// <summary>
    /// Retrieves the agent card for a given agent URL.
    /// </summary>
    /// <param name="agentPath"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken = default);
}
