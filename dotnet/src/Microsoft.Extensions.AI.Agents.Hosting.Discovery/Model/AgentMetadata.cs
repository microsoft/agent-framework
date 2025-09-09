// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

internal sealed class AgentMetadata
{
    /// <summary>
    /// Id for agent
    /// </summary>
    public required string Id { get; set; }

    /// <summary>
    /// name
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// descr
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// version
    /// </summary>
    public string? Version { get; set; }

    /// <summary>
    /// Custom metadata associated with the agent.
    /// </summary>
    public IDictionary<string, object>? CustomMetadata { get; set; }

    /// <summary>
    /// Definition of HTTP endpoints to call to trigger agent.
    /// </summary>
    public IList<HttpEndpointMetadata>? HttpEndpoints { get; set; }

    public static AgentMetadata FromGeneralMetadata(string id, GeneralMetadata generalMetadata)
    {
        return new AgentMetadata
        {
            Id = id,
            Name = generalMetadata.Name,
            Description = generalMetadata.Description,
            Version = generalMetadata.Version
        };
    }
}

internal sealed class HttpEndpointMetadata
{
    public required string Route { get; set; }
    public required string Method { get; set; }
}
