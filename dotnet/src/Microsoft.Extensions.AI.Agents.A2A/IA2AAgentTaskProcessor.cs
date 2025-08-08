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
public interface IA2AAgentTaskProcessor : IA2AAgentCardProvider
{
    /// <summary>
    /// todo
    /// </summary>
    /// <param name="task"></param>
    /// <param name="token"></param>
    /// <returns></returns>
    Task CreateTaskAsync(AgentTask task, CancellationToken token);

    /// <summary>
    /// todo
    /// </summary>
    /// <param name="task"></param>
    /// <param name="token"></param>
    /// <returns></returns>
    Task CancelTaskAsync(AgentTask task, CancellationToken token);

    /// <summary>
    /// todo
    /// </summary>
    /// <param name="task"></param>
    /// <param name="token"></param>
    /// <returns></returns>
    Task UpdateTaskAsync(AgentTask task, CancellationToken token);
}
