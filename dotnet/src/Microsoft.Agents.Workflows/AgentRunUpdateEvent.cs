// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents an event triggered when an agent run produces an update.
/// </summary>
public class AgentRunUpdateEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunUpdateEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="update">The agent run response update.</param>
    public AgentRunUpdateEvent(string executorId, AgentRunResponseUpdate update) : base(executorId, data: update)
    {
        this.Update = Throw.IfNull(update);
    }

    /// <summary>
    /// Gets the agent run response update.
    /// </summary>
    public AgentRunResponseUpdate Update { get; }

    /// <summary>
    /// Converts this event to an <see cref="AgentRunResponse"/> containing just this update.
    /// </summary>
    /// <returns></returns>
    public AgentRunResponse AsResponse()
    {
        IEnumerable<AgentRunResponseUpdate> updates = [this.Update];
        return updates.ToAgentRunResponse();
    }
}
