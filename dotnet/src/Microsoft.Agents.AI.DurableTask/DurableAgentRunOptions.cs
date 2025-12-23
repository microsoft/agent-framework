// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Options for running a durable agent.
/// </summary>
public sealed class DurableAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Gets or sets whether to enable tool calls for this request.
    /// </summary>
    public bool EnableToolCalls { get; set; } = true;

    /// <summary>
    /// Gets or sets the collection of tool names to enable. If not specified, all tools are enabled.
    /// </summary>
    public IList<string>? EnableToolNames { get; set; }

    /// <summary>
    /// Gets or sets the response format for the agent's response.
    /// </summary>
    public ChatResponseFormat? ResponseFormat { get; set; }

    /// <summary>
    /// Gets or sets whether to fire and forget the agent run request.
    /// </summary>
    /// <remarks>
    /// If <see cref="IsFireAndForget"/> is <c>true</c>, the agent run request will be sent and the method will return immediately.
    /// The caller will not wait for the agent to complete the run and will not receive a response. This setting is useful for
    /// long-running tasks where the caller does not need to wait for the agent to complete the run.
    /// </remarks>
    public bool IsFireAndForget { get; set; }
}
