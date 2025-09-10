// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

internal sealed class AgentDiscovery
{
    private readonly ConcurrentDictionary<ActorType, AgentMetadata> _actorMetadatas = new();

    public AgentDiscovery()
    {
    }

    internal void RegisterAgentDiscovery(ActorType actorType)
    {
        var agentMetadata = new AgentMetadata(actorType);
        if (!this._actorMetadatas.TryAdd(actorType, agentMetadata))
        {
            throw new System.ArgumentException($"An agent with the ID '{actorType}' has already been registered.", nameof(actorType));
        }
    }

    public ICollection<AgentMetadata> GetAllAgents()
    {
        return this._actorMetadatas.Values;
    }

    public bool TryGetAgent(string agentName, out AgentMetadata? agentMetadata)
        => this.TryGetAgent(new ActorType(agentName), out agentMetadata);

    public bool TryGetAgent(ActorType actorType, out AgentMetadata? agentMetadata)
        => this._actorMetadatas.TryGetValue(actorType, out agentMetadata);
}
