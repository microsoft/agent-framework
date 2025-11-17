// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides extension methods for registering and configuring AI agents in the context of the Azure Functions hosting environment.
/// </summary>
public static class DurableAgentsOptionsExtensions
{
    // Registry of agent options.
    private static readonly Dictionary<string, FunctionsAgentOptions> s_agentOptions = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Adds an AI agent to the specified DurableAgentsOptions instance and optionally configures agent-specific
    /// options.
    /// </summary>
    /// <param name="options">The DurableAgentsOptions instance to which the AI agent will be added.</param>
    /// <param name="agent">The AI agent to add. The agent's Name property must not be null or empty.</param>
    /// <param name="configure">An optional delegate to configure agent-specific options. If null, default options are used.</param>
    /// <returns>The updated <see cref="DurableAgentsOptions"/> instance containing the added AI agent.</returns>
    public static DurableAgentsOptions AddAIAgent(
        this DurableAgentsOptions options,
        AIAgent agent,
        Action<FunctionsAgentOptions>? configure)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrEmpty(agent.Name);

        // Initialize with default behavior (HTTP trigger enabled)
        FunctionsAgentOptions agentOptions = new() { HttpTrigger = { IsEnabled = true } };
        configure?.Invoke(agentOptions);
        options.AddAIAgent(agent);
        s_agentOptions[agent.Name] = agentOptions;
        return options;
    }

    /// <summary>
    /// Adds an AI agent to the specified options and configures trigger support for HTTP and MCP tool invocations.
    /// </summary>
    /// <remarks>If an agent with the same name already exists in the options, its configuration will be
    /// updated. Both triggers can be enabled independently. This method supports method chaining by returning the
    /// provided options instance.</remarks>
    /// <param name="options">The options collection to which the AI agent will be added. Cannot be null.</param>
    /// <param name="agent">The AI agent to add. The agent's Name property must not be null or empty.</param>
    /// <param name="enableHttpTrigger">true to enable an HTTP trigger for the agent; otherwise, false.</param>
    /// <param name="enableMcpToolTrigger">true to enable an MCP tool trigger for the agent; otherwise, false.</param>
    /// <returns>The updated <see cref="DurableAgentsOptions"/> instance with the specified AI agent and trigger configuration applied.</returns>
    public static DurableAgentsOptions AddAIAgent(
        this DurableAgentsOptions options,
        AIAgent agent,
        bool enableHttpTrigger,
        bool enableMcpToolTrigger)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrEmpty(agent.Name);

        FunctionsAgentOptions agentOptions = new();
        agentOptions.HttpTrigger.IsEnabled = enableHttpTrigger;
        agentOptions.McpToolTrigger.IsEnabled = enableMcpToolTrigger;

        options.AddAIAgent(agent);
        s_agentOptions[agent.Name] = agentOptions;
        return options;
    }

    /// <summary>
    /// Registers an AI agent factory with the specified name and optional configuration in the provided
    /// DurableAgentsOptions instance.
    /// </summary>
    /// <remarks>If an agent factory with the same name already exists, its configuration will be replaced.
    /// This method enables custom agent registration and configuration for use in durable agent scenarios.</remarks>
    /// <param name="options">The DurableAgentsOptions instance to which the AI agent factory will be added. Cannot be null.</param>
    /// <param name="name">The unique name used to identify the AI agent factory. Cannot be null.</param>
    /// <param name="factory">A delegate that creates an AIAgent instance using the provided IServiceProvider. Cannot be null.</param>
    /// <param name="configure">An optional action to configure FunctionsAgentOptions for the agent factory. If null, default options are used.</param>
    /// <returns>The updated DurableAgentsOptions instance containing the registered AI agent factory.</returns>
    public static DurableAgentsOptions AddAIAgentFactory(
        this DurableAgentsOptions options,
        string name,
        Func<IServiceProvider, AIAgent> factory,
        Action<FunctionsAgentOptions>? configure)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(factory);

        // Initialize with default behavior (HTTP trigger enabled)
        FunctionsAgentOptions agentOptions = new() { HttpTrigger = { IsEnabled = true } };
        configure?.Invoke(agentOptions);
        options.AddAIAgentFactory(name, factory);
        s_agentOptions[name] = agentOptions;
        return options;
    }

    /// <summary>
    /// Registers an AI agent factory with the specified name and configures trigger options for the agent.
    /// </summary>
    /// <remarks>If both triggers are disabled, the agent will not be accessible via HTTP or MCP tool
    /// endpoints. This method can be used to register multiple agent factories with different configurations.</remarks>
    /// <param name="options">The options object to which the AI agent factory will be added. Cannot be null.</param>
    /// <param name="name">The unique name used to identify the AI agent factory. Cannot be null.</param>
    /// <param name="factory">A delegate that creates an instance of the AI agent using the provided service provider. Cannot be null.</param>
    /// <param name="enableHttpTrigger">true to enable the HTTP trigger for the agent; otherwise, false.</param>
    /// <param name="enableMcpToolTrigger">true to enable the MCP tool trigger for the agent; otherwise, false.</param>
    /// <returns>The same DurableAgentsOptions instance, allowing for method chaining.</returns>
    public static DurableAgentsOptions AddAIAgentFactory(
        this DurableAgentsOptions options,
        string name,
        Func<IServiceProvider, AIAgent> factory,
        bool enableHttpTrigger,
        bool enableMcpToolTrigger)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(factory);

        FunctionsAgentOptions agentOptions = new();
        agentOptions.HttpTrigger.IsEnabled = enableHttpTrigger;
        agentOptions.McpToolTrigger.IsEnabled = enableMcpToolTrigger;

        options.AddAIAgentFactory(name, factory);
        s_agentOptions[name] = agentOptions;
        return options;
    }

    /// <summary>
    /// Builds the agentOptions used for dependency injection (read-only copy).
    /// </summary>
    internal static IReadOnlyDictionary<string, FunctionsAgentOptions> GetAgentOptionsSnapshot()
    {
        return new Dictionary<string, FunctionsAgentOptions>(s_agentOptions, StringComparer.OrdinalIgnoreCase);
    }
}
