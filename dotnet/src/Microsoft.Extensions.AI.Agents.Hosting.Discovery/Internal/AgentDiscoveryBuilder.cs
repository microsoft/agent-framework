// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

internal sealed class AgentDiscoveryBuilder : IAgentDiscoveryBuilder
{
    public string AgentId { get; set; }

    public AgentDiscoveryBuilder(string agentId)
    {
        this.AgentId = agentId;
    }
}
