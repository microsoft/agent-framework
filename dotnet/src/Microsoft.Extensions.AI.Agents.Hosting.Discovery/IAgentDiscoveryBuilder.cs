// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Provides discovery configuration options for <see cref="AIAgent"/>
/// </summary>
public interface IAgentDiscoveryBuilder
{
    /// <summary>
    /// The id of the agent that is being configured for discovery.
    /// </summary>
    string AgentId { get; set; }
}
