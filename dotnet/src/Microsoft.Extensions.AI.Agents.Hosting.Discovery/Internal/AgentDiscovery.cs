// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

/// <summary>
/// we should rename it; it should hold all agents
/// </summary>
internal sealed class AgentDiscovery
{
    private readonly IServiceCollection _services;

    private readonly ConcurrentDictionary<ActorType, AgentMetadata> _actorMetadatas = new();

    public AgentDiscovery(IServiceCollection services)
    {
        this._services = services;
    }

    public void RegisterAgentDiscovery(ActorType actorType, GeneralMetadata general)
    {
        var metadata = this._actorMetadatas.GetOrAdd(actorType, actorType => new AgentMetadata() { Name = actorType.Name });

        metadata.Name ??= general.Name;
        metadata.Description = general.Description;
        metadata.Instructions = general.Instructions;
    }

    public void IncludeEndpoints(ActorType actorType, EndpointsMetadata? endpointsMetadata)
    {
        if (!this._actorMetadatas.TryGetValue(actorType, out var metadata))
        {
            throw new KeyNotFoundException("Agent is not registered");
        }

        endpointsMetadata ??= EndpointsMetadata.AgentFrameworkDefaultEndpointsMetadata;

        // set values
        metadata.Endpoints ??= new();
        metadata.Endpoints.Path = endpointsMetadata.Path;
    }

    public IReadOnlyCollection<AgentMetadata> GetAgentsMetadata()
    {
        return (IReadOnlyCollection<AgentMetadata>)this._actorMetadatas.Values;
    }
}
