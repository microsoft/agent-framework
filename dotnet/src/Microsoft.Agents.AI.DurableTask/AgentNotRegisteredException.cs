// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Exception thrown when an agent with the specified name has not been registered.
/// </summary>
public sealed class AgentNotRegisteredException : InvalidOperationException
{
    // Not used, but required by static analysis.
    private AgentNotRegisteredException()
    {
        this.AgentName = string.Empty;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentNotRegisteredException"/> class with the agent name.
    /// </summary>
    /// <param name="agentName">The name of the agent that was not registered.</param>
    public AgentNotRegisteredException(string agentName)
        : base(GetMessage(agentName))
    {
        this.AgentName = agentName;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentNotRegisteredException"/> class with the agent name and an inner exception.
    /// </summary>
    /// <param name="agentName">The name of the agent that was not registered.</param>
    /// <param name="innerException">The exception that is the cause of the current exception.</param>
    public AgentNotRegisteredException(string agentName, Exception? innerException)
        : base(GetMessage(agentName), innerException)
    {
        this.AgentName = agentName;
    }

    /// <summary>
    /// Gets the name of the agent that was not registered.
    /// </summary>
    public string AgentName { get; }

    private static string GetMessage(string agentName)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentName);
        return $"No agent named '{agentName}' was registered. Ensure the agent is registered using {nameof(ServiceCollectionExtensions.ConfigureDurableAgents)} before using it in an orchestration.";
    }
}
