// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents an event triggered when an agent run produces an update.
/// </summary>
public class AgentResponseUpdateEvent : WorkflowOutputEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseUpdateEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="update">The agent run response update.</param>
    public AgentResponseUpdateEvent(string executorId, AgentResponseUpdate update) : base(update, executorId)
    {
        this.Update = Throw.IfNull(update);
    }

    /// <summary>
    /// Gets the agent run response update.
    /// </summary>
    public AgentResponseUpdate Update { get; }

    /// <summary>
    /// Converts this event to an <see cref="AgentResponse"/> containing just this update.
    /// </summary>
    /// <returns></returns>
    public AgentResponse AsResponse()
    {
        IEnumerable<AgentResponseUpdate> updates = [this.Update];
        return updates.ToAgentResponse();
    }
}
