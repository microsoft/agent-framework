// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents an event triggered when an agent run produces an update.
/// </summary>
public sealed class AgentResponseUpdateEvent : WorkflowOutputEvent
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
    /// Initializes a new instance of the <see cref="AgentResponseUpdateEvent"/> class with the given output tag.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="update">The agent run response update.</param>
    /// <param name="tag">The output tag to associate with this event.</param>
    public AgentResponseUpdateEvent(string executorId, AgentResponseUpdate update, OutputTag tag) : base(update, executorId, tag)
    {
        this.Update = Throw.IfNull(update);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseUpdateEvent"/> class with the given output tags.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="update">The agent run response update.</param>
    /// <param name="tags">The output tags to associate with this event. May be <see langword="null"/> or empty.</param>
    public AgentResponseUpdateEvent(string executorId, AgentResponseUpdate update, IEnumerable<OutputTag>? tags) : base(update, executorId, tags)
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
