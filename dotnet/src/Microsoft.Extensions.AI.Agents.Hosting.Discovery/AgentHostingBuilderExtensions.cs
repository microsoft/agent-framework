// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Extensions for <see cref="IAgentHostingBuilder"/>
/// </summary>
public static class AgentHostingBuilderExtensions
{
    /// <summary>
    /// Adds <see cref="AIAgent"/> to the discovery services exposing the agent metadata via discovery endpoints.
    /// </summary>
    /// <param name="builder">The builder for the <see cref="AIAgent"/></param>
    /// <param name="generalMetadata"></param>
    public static IAgentDiscoveryBuilder WithDiscovery(this IAgentHostingBuilder builder, GeneralMetadata generalMetadata)
    {
        var agentDiscovery = InitializeAgentsDiscoveryProvider(builder.Services);

        var agentId = generalMetadata.Id ?? builder.ActorType.Name;
        agentDiscovery.RegisterAgentDiscovery(agentId, generalMetadata);

        return new AgentDiscoveryBuilder(agentId);
    }

    private static AgentDiscovery InitializeAgentsDiscoveryProvider(IServiceCollection services)
    {
        Throw.IfNull(services);

        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is AgentDiscovery);
        if (descriptor?.ImplementationInstance is not AgentDiscovery instance)
        {
            instance = new AgentDiscovery();
            services.Add(ServiceDescriptor.Singleton(instance));
            // instance.ConfigureServices(services);
        }

        return instance;
    }
}
