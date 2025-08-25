// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

/// <summary>
/// Represents data about endpoints
/// </summary>
public sealed class EndpointsMetadata
{
    /// <summary>
    /// Default metadata for agent framework.
    /// </summary>
    public static EndpointsMetadata AgentFrameworkDefaultEndpointsMetadata { get; } = new();

    /// <summary>
    /// Path
    /// </summary>
    public string? Path { get; }
}
