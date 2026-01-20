// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents an event triggered when an agent produces a response.
/// </summary>
public class AgentResponseEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response">The agent response.</param>
    public AgentResponseEvent(string executorId, AgentResponse response) : base(executorId, data: response)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Gets the agent response.
    /// </summary>
    public AgentResponse Response { get; }
}
