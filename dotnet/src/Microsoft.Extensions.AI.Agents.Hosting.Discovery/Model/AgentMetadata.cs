// Copyright (c) Microsoft. All rights reserved.

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
