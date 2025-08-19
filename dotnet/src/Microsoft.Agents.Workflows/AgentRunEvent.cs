// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event triggered when an agent run is completed.
/// </summary>
public class AgentRunEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response"></param>
    public AgentRunEvent(string executorId, AgentRunResponse? response = null) : base(executorId, data: response)
    {
        this.Response = response;
    }

    /// <summary>
    /// Gets the content of the agent response.
    /// </summary>
    public AgentRunResponse? Response { get; }
}
