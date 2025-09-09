// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Builders;
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
    public static IAgentDiscoveryBuilder WithDiscovery(this IAgentHostingBuilder builder, GeneralMetadata? generalMetadata = null)
    {
        var agentDiscovery = builder.Services.InitializeAgentsDiscoveryProvider();

        var agentId = generalMetadata?.Id ?? builder.ActorType.Name;
        var metadata = generalMetadata ?? BuildUpGeneralMetadata(agentId, builder);

        agentDiscovery.RegisterAgentDiscovery(agentId, metadata);
        return new AgentDiscoveryBuilder(agentId, builder.Services);
    }

    private static GeneralMetadata BuildUpGeneralMetadata(string agentId, IAgentHostingBuilder builder)
    {
        return builder switch
        {
            ChatClientAgentHostingBuilder chatClientBuilder => new()
            {
                Id = agentId,
                Name = chatClientBuilder.ActorType.Name,
                Description = chatClientBuilder.Description,
            },

            _ => new()
            {
                Id = agentId,
                Name = builder.ActorType.Name
            }
        };
    }

    internal static AgentDiscovery InitializeAgentsDiscoveryProvider(this IServiceCollection services)
    {
        Throw.IfNull(services);

        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is AgentDiscovery);
        if (descriptor?.ImplementationInstance is not AgentDiscovery instance)
        {
            instance = new AgentDiscovery();
            services.Add(ServiceDescriptor.Singleton(instance));
        }

        return instance;
    }
}
