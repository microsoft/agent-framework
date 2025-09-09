// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Net.Http;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Extensions for <see cref="IAgentDiscoveryBuilder"/>
/// </summary>
public static class AgentDiscoveryBuilderExtensions
{
    /// <summary>
    /// Adds custom metadata to the agent metadata
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="metadata"></param>
    /// <returns></returns>
    public static IAgentDiscoveryBuilder WithMetadata(this IAgentDiscoveryBuilder builder, Dictionary<string, object> metadata)
    {
        var agentDiscovery = builder.Services.InitializeAgentsDiscoveryProvider();
        agentDiscovery.AddCustomMetadata(builder.AgentId, metadata);

        return builder;
    }

    public static IAgentDiscoveryBuilder WithHttpEndpoint(this IAgentDiscoveryBuilder builder, string route, HttpMethod method)
    {
        var agentDiscovery = builder.Services.InitializeAgentsDiscoveryProvider();
        agentDiscovery.AddCustomMetadata(builder.AgentId, metadata);

        return builder;
    }
}
