// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents an event triggered when an agent produces a response.
/// </summary>
public sealed class AgentResponseEvent : WorkflowOutputEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response">The agent response.</param>
    public AgentResponseEvent(string executorId, AgentResponse response) : base(response, executorId)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseEvent"/> class with the given output tag.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response">The agent response.</param>
    /// <param name="tag">The output tag to associate with this event.</param>
    public AgentResponseEvent(string executorId, AgentResponse response, OutputTag tag) : base(response, executorId, tag)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponseEvent"/> class with the given output tags.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response">The agent response.</param>
    /// <param name="tags">The output tags to associate with this event. May be <see langword="null"/> or empty.</param>
    public AgentResponseEvent(string executorId, AgentResponse response, IEnumerable<OutputTag>? tags) : base(response, executorId, tags)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Gets the agent response.
    /// </summary>
    public AgentResponse Response { get; }
}
