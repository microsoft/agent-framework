// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

/// <summary>
/// Represents the discovery metadata for specific <see cref="AIAgent"/>
/// </summary>
internal sealed class AgentMetadata
{
    /// <summary>
    /// id
    /// </summary>
    public required string? Name { get; set; }

    /// <summary>
    /// descr
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// instr
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// end
    /// </summary>
    public Endpoints? Endpoints { get; set; }
}

internal sealed class Endpoints
{
    public string? Path { get; set; }
}
