// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Defines the handoff relationships for a given agent.
/// Maps target agent names/IDs to handoff descriptions.
/// </summary>
public sealed class AgentHandoffs : Dictionary<string, string>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentHandoffs"/> class with no handoff relationships.
    /// </summary>
    public AgentHandoffs() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentHandoffs"/> class with the specified handoff relationships.
    /// </summary>
    /// <param name="handoffs">A dictionary mapping target agent names/IDs to handoff descriptions.</param>
    public AgentHandoffs(Dictionary<string, string> handoffs) : base(handoffs) { }
}

/// <summary>
/// Defines the orchestration handoff relationships for all agents in the system.
/// Maps source agent names/IDs to their <see cref="AgentHandoffs"/>.
/// </summary>
public sealed class OrchestrationHandoffs : Dictionary<string, AgentHandoffs>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="OrchestrationHandoffs"/> class with no handoff relationships.
    /// </summary>
    /// <param name="firstAgent">The first agent to be invoked (prior to any handoff).</param>
    public OrchestrationHandoffs(AIAgent firstAgent)
        : this(firstAgent.Name ?? firstAgent.Id)
    {
        this.Agents.Add(firstAgent);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="OrchestrationHandoffs"/> class with no handoff relationships.
    /// </summary>
    /// <param name="firstAgentName">The name of the first agent to be invoked (prior to any handoff).</param>
    public OrchestrationHandoffs(string firstAgentName)
    {
        Throw.IfNullOrWhitespace(firstAgentName, nameof(firstAgentName));
        this.FirstAgentName = firstAgentName;
    }

    /// <summary>
    /// The name of the first agent to be invoked (prior to any handoff).
    /// </summary>
    public string FirstAgentName { get; }

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// Each target agent's name or ID is mapped to its description.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public static OrchestrationHandoffs StartWith(AIAgent source) => new(source);

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// Each target agent's name or ID is mapped to its description.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <param name="targets">The target agents to add as handoff targets for the source agent.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public OrchestrationHandoffs Add(AIAgent source, params AIAgent[] targets)
    {
        string key = source.Name ?? source.Id;

        AgentHandoffs agentHandoffs = this.GetAgentHandoffs(key);

        foreach (AIAgent target in targets)
        {
            if (string.IsNullOrWhiteSpace(target.Description) && string.IsNullOrWhiteSpace(target.Name))
            {
                throw new InvalidOperationException($"The provided target agent with Id '{target.Id}' has no description or name, and no handoff description has been provided. At least one of these are required to register a handoff so that the appropriate target agent can be chosen.");
            }

            this.Agents.Add(target);
            agentHandoffs[target.Name ?? target.Id] = target.Description ?? target.Name!;
        }

        this.Agents.Add(source);

        return this;
    }

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent with a custom description.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <param name="target">The target agent.</param>
    /// <param name="description">The handoff description.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public OrchestrationHandoffs Add(AIAgent source, AIAgent target, string description)
        => this.Add(source.Name ?? source.Id, target.Name ?? target.Id, description);

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent name/ID with a custom description.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <param name="targetName">The target agent's name or ID.</param>
    /// <param name="description">The handoff description.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public OrchestrationHandoffs Add(AIAgent source, string targetName, string description)
        => this.Add(source.Name ?? source.Id, targetName, description);

    /// <summary>
    /// Adds a handoff relationship from a source agent name/ID to a target agent name/ID with a custom description.
    /// </summary>
    /// <param name="sourceName">The source agent's name or ID.</param>
    /// <param name="targetName">The target agent's name or ID.</param>
    /// <param name="description">The handoff description.</param>
    /// <returns>The updated <see cref="OrchestrationHandoffs"/> instance.</returns>
    public OrchestrationHandoffs Add(string sourceName, string targetName, string description)
    {
        AgentHandoffs agentHandoffs = this.GetAgentHandoffs(sourceName);
        agentHandoffs[targetName] = description;

        return this;
    }

    private AgentHandoffs GetAgentHandoffs(string key)
    {
        if (!this.TryGetValue(key, out AgentHandoffs? agentHandoffs))
        {
            this[key] = agentHandoffs = [];
        }

        return agentHandoffs;
    }

    internal HashSet<AIAgent> Agents { get; } = [];
}

/// <summary>
/// Handoff relationships post-processed into a name-based lookup table that includes the agent type and handoff description.
/// Maps agent names/IDs to a tuple of <see cref="ActorType"/> and handoff description.
/// </summary>
internal sealed class HandoffLookup : Dictionary<string, (ActorType AgentType, string Description)>;
