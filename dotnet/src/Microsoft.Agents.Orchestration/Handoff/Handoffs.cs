// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.SemanticKernel.Agents.Runtime;

namespace Microsoft.Agents.Orchestration.Handoff;

/// <summary>
/// Defines the handoff relationships for a given agent.
/// Maps target agent to handoff descriptions.
/// </summary>
public sealed class AgentHandoffs : Dictionary<Agent, string>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentHandoffs"/> class with no handoff relationships.
    /// </summary>
    public AgentHandoffs() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentHandoffs"/> class with the specified handoff relationships.
    /// </summary>
    /// <param name="handoffs">A dictionary mapping target agent to handoff descriptions.</param>
    public AgentHandoffs(Dictionary<Agent, string> handoffs) : base(handoffs) { }
}

/// <summary>
/// Defines the orchestration handoff relationships for all agents in the system.
/// Maps source agent names/IDs to their <see cref="AgentHandoffs"/>.
/// </summary>
public sealed class OrchestrationHandoffs : Dictionary<Agent, AgentHandoffs>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="OrchestrationHandoffs"/> class with no handoff relationships.
    /// </summary>
    /// <param name="firstAgent">The first agent to be invoked (prior to any handoff).</param>
    public OrchestrationHandoffs(Agent firstAgent)
    {
        this.FirstAgent = firstAgent;
    }

    /// <summary>
    /// The name of the first agent to be invoked (prior to any handoff).
    /// </summary>
    public Agent FirstAgent { get; }

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// Each target agent's name or ID is mapped to its description.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public static OrchestrationHandoffs StartWith(Agent source) => new(source);
}

/// <summary>
/// Extension methods for building and modifying <see cref="OrchestrationHandoffs"/> relationships.
/// </summary>
public static class OrchestrationHandoffsExtensions
{
    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// Each target agent's name or ID is mapped to its description.
    /// </summary>
    /// <param name="handoffs">The orchestration handoffs collection to update.</param>
    /// <param name="source">The source agent.</param>
    /// <param name="targets">The target agents to add as handoff targets for the source agent.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public static OrchestrationHandoffs Add(this OrchestrationHandoffs handoffs, Agent source, params Agent[] targets)
    {
        string key = source.Name ?? source.Id;

        AgentHandoffs agentHandoffs = handoffs.GetAgentHandoffs(source);

        foreach (Agent target in targets)
        {
            agentHandoffs[target] = target.Description ?? string.Empty;
        }

        return handoffs;
    }

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent with a custom description.
    /// </summary>
    /// <param name="handoffs">The orchestration handoffs collection to update.</param>
    /// <param name="source">The source agent.</param>
    /// <param name="target">The target agent.</param>
    /// <param name="description">The handoff description.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public static OrchestrationHandoffs Add(this OrchestrationHandoffs handoffs, Agent source, Agent target, string description)
    {
        AgentHandoffs agentHandoffs = handoffs.GetAgentHandoffs(source);
        agentHandoffs[target] = description;

        return handoffs;
    }

    private static AgentHandoffs GetAgentHandoffs(this OrchestrationHandoffs handoffs, Agent key)
    {
        if (!handoffs.TryGetValue(key, out AgentHandoffs? agentHandoffs))
        {
            agentHandoffs = [];
            handoffs[key] = agentHandoffs;
        }

        return agentHandoffs;
    }
}

/// <summary>
/// Handoff relationships post-processed into a name-based lookup table that includes the agent type and handoff description.
/// Maps agent names/IDs to a tuple of <see cref="AgentType"/> and handoff description.
/// </summary>
internal sealed class HandoffLookup : Dictionary<Agent, (AgentType AgentType, string Description)>;
