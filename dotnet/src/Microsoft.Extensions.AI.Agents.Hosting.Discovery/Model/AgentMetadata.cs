// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

internal sealed class AgentMetadata
{
    /// <summary>
    /// Id for agent
    /// </summary>
    public ActorType Name { get; }

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
    /// Custom metadata associated with the agent.
    /// </summary>
    public IDictionary<string, object>? CustomMetadata { get; set; }
}
