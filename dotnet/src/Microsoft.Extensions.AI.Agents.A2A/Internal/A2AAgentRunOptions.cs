// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal sealed class A2AAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Keeps the taskId for the A2A task. Is required to run the agent correctly with A2A integration.
    /// </summary>
    public string? TaskId { get; init; }

    private A2AAgentRunOptions(string? taskId)
    {
        this.TaskId = taskId;
    }

    public static A2AAgentRunOptions CreateA2AMessagingOptions()
        => new(taskId: null);

    public static A2AAgentRunOptions CreateA2AAgentTaskOptions(AgentTask agentTask)
        => new(agentTask.Id);
}
