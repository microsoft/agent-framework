// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides contextual information about the agent and session to an <see cref="AgentSkillsSource"/>
/// when retrieving skills.
/// </summary>
public sealed class AgentSkillsSourceContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsSourceContext"/> class.
    /// </summary>
    /// <param name="agent">The agent requesting skills.</param>
    /// <param name="session">The session associated with the agent invocation, if any.</param>
    public AgentSkillsSourceContext(AIAgent agent, AgentSession? session)
    {
        this.Agent = Throw.IfNull(agent);
        this.Session = session;
    }

    /// <summary>
    /// Gets the agent requesting skills.
    /// </summary>
    public AIAgent Agent { get; }

    /// <summary>
    /// Gets the session associated with the agent invocation, if any.
    /// </summary>
    public AgentSession? Session { get; }
}
