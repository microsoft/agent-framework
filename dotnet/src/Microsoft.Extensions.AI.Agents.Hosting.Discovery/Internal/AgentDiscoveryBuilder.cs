// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

internal sealed class AgentDiscoveryBuilder : IAgentDiscoveryBuilder
{
    public string AgentId { get; set; }

    public IServiceCollection Services { get; }

    public AgentDiscoveryBuilder(string agentId, IServiceCollection services)
    {
        this.AgentId = agentId;
        this.Services = services;
    }
}
