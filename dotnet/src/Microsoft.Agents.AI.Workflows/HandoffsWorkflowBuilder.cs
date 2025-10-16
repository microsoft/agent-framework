// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a builder for specifying the handoff relationships between agents and building the resulting workflow.
/// </summary>
public sealed class HandoffsWorkflowBuilder
{
    internal const string FunctionPrefix = "handoff_to_";
    private readonly AIAgent _initialAgent;
    private readonly Dictionary<AIAgent, HashSet<HandoffTarget>> _targets = [];
    private readonly HashSet<AIAgent> _allAgents = new(AIAgentIDEqualityComparer.Instance);

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffsWorkflowBuilder"/> class with no handoff relationships.
    /// </summary>
    /// <param name="initialAgent">The first agent to be invoked (prior to any handoff).</param>
    internal HandoffsWorkflowBuilder(AIAgent initialAgent)
    {
        this._initialAgent = initialAgent;
        this._allAgents.Add(initialAgent);
    }

    /// <summary>
    /// Gets or sets additional instructions to provide to an agent that has handoffs about how and when to perform them.
    /// </summary>
    /// <remarks>
    /// By default, simple instructions are included. This may be set to <see langword="null"/> to avoid including
    /// any additional instructions, or may be customized to provide more specific guidance.
    /// </remarks>
    public string? HandoffInstructions { get; set; } =
         $"""
              You are one agent in a multi-agent system. You can hand off the conversation to another agent if appropriate. Handoffs are achieved
              by calling a handoff function, named in the form `{FunctionPrefix}<agent_id>`; the description of the function provides details on the
              target agent of that handoff. Handoffs between agents are handled seamlessly in the background; never mention or narrate these handoffs
              in your conversation with the user.
              """;

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// </summary>
    /// <param name="from">The source agent.</param>
    /// <param name="to">The target agents to add as handoff targets for the source agent.</param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    /// <remarks>The handoff reason for each target in <paramref name="to"/> is derived from that agent's description or name.</remarks>
    public HandoffsWorkflowBuilder WithHandoffs(AIAgent from, IEnumerable<AIAgent> to)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        foreach (var target in to)
        {
            if (target is null)
            {
                Throw.ArgumentNullException(nameof(to), "One or more target agents are null.");
            }

            this.WithHandoff(from, target);
        }

        return this;
    }

    /// <summary>
    /// Adds handoff relationships from one or more sources agent to a target agent.
    /// </summary>
    /// <param name="from">The source agents.</param>
    /// <param name="to">The target agent to add as a handoff target for each source agent.</param>
    /// <param name="handoffReason">
    /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
    /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
    /// </param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    public HandoffsWorkflowBuilder WithHandoffs(IEnumerable<AIAgent> from, AIAgent to, string? handoffReason = null)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        foreach (var source in from)
        {
            if (source is null)
            {
                Throw.ArgumentNullException(nameof(from), "One or more source agents are null.");
            }

            this.WithHandoff(source, to, handoffReason);
        }

        return this;
    }

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent with a custom handoff reason.
    /// </summary>
    /// <param name="from">The source agent.</param>
    /// <param name="to">The target agent.</param>
    /// <param name="handoffReason">
    /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
    /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
    /// </param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    public HandoffsWorkflowBuilder WithHandoff(AIAgent from, AIAgent to, string? handoffReason = null)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        this._allAgents.Add(from);
        this._allAgents.Add(to);

        if (!this._targets.TryGetValue(from, out var handoffs))
        {
            this._targets[from] = handoffs = [];
        }

        if (string.IsNullOrWhiteSpace(handoffReason))
        {
            handoffReason = to.Description ?? to.Name ?? (to as ChatClientAgent)?.Instructions;
            if (string.IsNullOrWhiteSpace(handoffReason))
            {
                Throw.ArgumentException(
                    nameof(to),
                    $"The provided target agent '{to.DisplayName}' has no description, name, or instructions, and no handoff description has been provided. " +
                    "At least one of these is required to register a handoff so that the appropriate target agent can be chosen.");
            }
        }

        if (!handoffs.Add(new(to, handoffReason)))
        {
            Throw.InvalidOperationException($"A handoff from agent '{from.DisplayName}' to agent '{to.DisplayName}' has already been registered.");
        }

        return this;
    }

    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of agents that operate via handoffs, with the next
    /// agent to process messages selected by the current agent.
    /// </summary>
    /// <returns>The workflow built based on the handoffs in the builder.</returns>
    public Workflow Build()
    {
        HandoffsStartExecutor start = new();
        HandoffsEndExecutor end = new();
        WorkflowBuilder builder = new(start);

        // Create an AgentExecutor for each again.
        Dictionary<string, HandoffAgentExecutor> executors = this._allAgents.ToDictionary(a => a.Id, a => new HandoffAgentExecutor(a, this.HandoffInstructions));

        // Connect the start executor to the initial agent.
        builder.AddEdge(start, executors[this._initialAgent.Id]);

        // Initialize each executor with its handoff targets to the other executors.
        foreach (var agent in this._allAgents)
        {
            executors[agent.Id].Initialize(builder, end, executors,
                this._targets.TryGetValue(agent, out HashSet<HandoffTarget>? targets) ? targets : []);
        }

        // Build the workflow.
        return builder.WithOutputFrom(end).Build();
    }
}
