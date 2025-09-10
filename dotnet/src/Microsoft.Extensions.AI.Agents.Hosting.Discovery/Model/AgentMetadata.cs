// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

/// <summary>
/// Representation of metadata for the <see cref="AIAgent"/>
/// </summary>
public sealed class AgentMetadata
{
    /// <summary>
    /// Id for agent
    /// </summary>
    public ActorType Name { get; }

    /// <summary>
    /// Initializes the agent metadata with the specified <see cref="ActorType"/>.
    /// </summary>
    /// <param name="name"></param>
    public AgentMetadata(ActorType name)
    {
        this.Name = name;
    }

    /// <summary>
    /// descr
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// version
    /// </summary>
    public string? Version { get; set; }

    /// <summary>
    /// If applicable, the instructions supplied to the agent.
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// The underlying model used by the agent
    /// </summary>
    public string? Model { get; set; }

    /// <summary>
    /// Custom metadata associated with the agent.
    /// </summary>
    public IDictionary<string, object>? CustomMetadata { get; set; }
}
