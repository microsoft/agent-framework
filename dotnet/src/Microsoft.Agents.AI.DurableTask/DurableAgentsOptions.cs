// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Builder for configuring durable agents.
/// </summary>
public sealed class DurableAgentsOptions
{
    // Agent names are case-insensitive
    private readonly Dictionary<string, Func<IServiceProvider, AIAgent>> _agentFactories = new(StringComparer.OrdinalIgnoreCase);

    internal DurableAgentsOptions()
    {
    }

    /// <summary>
    /// Adds an AI agent factory to the options.
    /// </summary>
    /// <param name="name">The name of the agent.</param>
    /// <param name="factory">The factory function to create the agent.</param>
    /// <returns>The options instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="name"/> or <paramref name="factory"/> is null.</exception>
    public DurableAgentsOptions AddAIAgentFactory(string name, Func<IServiceProvider, AIAgent> factory)
    {
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(factory);
        this._agentFactories.Add(name, factory);
        return this;
    }

    /// <summary>
    /// Adds a list of AI agents to the options.
    /// </summary>
    /// <param name="agents">The list of agents to add.</param>
    /// <returns>The options instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agents"/> is null.</exception>
    public DurableAgentsOptions AddAIAgents(params IEnumerable<AIAgent> agents)
    {
        ArgumentNullException.ThrowIfNull(agents);
        foreach (AIAgent agent in agents)
        {
            this.AddAIAgent(agent);
        }

        return this;
    }

    /// <summary>
    /// Adds an AI agent to the options.
    /// </summary>
    /// <param name="agent">The agent to add.</param>
    /// <returns>The options instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> is null.</exception>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="agent.Name"/> is null or whitespace or when an agent with the same name has already been registered.
    /// </exception>
    public DurableAgentsOptions AddAIAgent(AIAgent agent)
    {
        ArgumentNullException.ThrowIfNull(agent);

        if (string.IsNullOrWhiteSpace(agent.Name))
        {
            throw new ArgumentException($"{nameof(agent.Name)} must not be null or whitespace.", nameof(agent));
        }

        if (this._agentFactories.ContainsKey(agent.Name))
        {
            throw new ArgumentException($"An agent with name '{agent.Name}' has already been registered.", nameof(agent));
        }

        this._agentFactories.Add(agent.Name, sp => agent);
        return this;
    }

    /// <summary>
    /// Gets the agents that have been added to this builder.
    /// </summary>
    /// <returns>A read-only collection of agents.</returns>
    internal IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> GetAgentFactories()
    {
        return this._agentFactories.AsReadOnly();
    }
}
