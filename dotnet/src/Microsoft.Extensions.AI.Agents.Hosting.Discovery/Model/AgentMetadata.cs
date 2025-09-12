// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

/// <summary>
/// Representation of metadata for the <see cref="AIAgent"/>
/// </summary>
public sealed class AgentMetadata
{
    /// <summary>
    /// Name of the agent
    /// </summary>
    [JsonPropertyName("name")]
    public ActorType Name { get; }

    /// <summary>
    /// Initializes the agent metadata with the specified <see cref="ActorType"/>.
    /// </summary>
    public AgentMetadata(ActorType name)
    {
        this.Name = name;
    }

    /// <summary>
    /// Description of the agent.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }

    /// <summary>
    /// Agent definition version.
    /// </summary>
    [JsonPropertyName("version")]
    public string? Version { get; set; }

    /// <summary>
    /// If applicable, the instructions supplied to the agent.
    /// </summary>
    [JsonPropertyName("instructions")]
    public string? Instructions { get; set; }

    /// <summary>
    /// The underlying model used by the agent
    /// </summary>
    [JsonPropertyName("model")]
    public string? Model { get; set; }

    /// <summary>
    /// Custom metadata associated with the agent.
    /// </summary>
    [JsonPropertyName("metadata")]
    public IDictionary<string, object>? Metadata { get; set; }
}
