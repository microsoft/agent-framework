// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

internal sealed class AgentDiscovery
{
    private readonly ConcurrentDictionary<string, AgentMetadata> _actorMetadatas = new();

    public AgentDiscovery()
    {
    }

    internal void RegisterAgentDiscovery(string agentId, GeneralMetadata generalMetadata)
    {
        var agentMetadata = AgentMetadata.FromGeneralMetadata(agentId, generalMetadata);
        if (!this._actorMetadatas.TryAdd(agentId, agentMetadata))
        {
            throw new System.ArgumentException($"An agent with the ID '{agentId}' has already been registered.", nameof(agentId));
        }
    }

    public ICollection<AgentMetadata> GetAllAgents()
    {
        return this._actorMetadatas.Values;
    }
}
