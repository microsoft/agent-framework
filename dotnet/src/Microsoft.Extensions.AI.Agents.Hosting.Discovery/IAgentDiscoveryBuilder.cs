// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Provides discovery configuration options for <see cref="AIAgent"/>
/// </summary>
public interface IAgentDiscoveryBuilder
{
    /// <summary>
    /// services
    /// </summary>
    IServiceCollection Services { get; }

    /// <summary>
    /// The id of the agent that is being configured for discovery.
    /// </summary>
    string AgentId { get; set; }
}
