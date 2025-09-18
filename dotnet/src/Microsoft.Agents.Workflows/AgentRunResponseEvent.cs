// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents an event triggered when an agent run produces an update.
/// </summary>
public class AgentRunResponseEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunUpdateEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response">The agent run response.</param>
    public AgentRunResponseEvent(string executorId, AgentRunResponse response) : base(executorId, data: response)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Gets the agent run response.
    /// </summary>
    public AgentRunResponse Response { get; }
}
