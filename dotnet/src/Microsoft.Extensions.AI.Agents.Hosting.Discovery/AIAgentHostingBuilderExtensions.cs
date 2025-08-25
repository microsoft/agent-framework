// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Builders;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Extensions for <see cref="IAIAgentHostingBuilder"/>
/// </summary>
public static class AIAgentHostingBuilderExtensions
{
    /// <summary>
    /// Adds <see cref="AIAgent"/> to the discovery services exposing the agent metadata via discovery endpoints.
    /// </summary>
    /// <param name="builder">The builder for the <see cref="AIAgent"/></param>
    /// <param name="generalMetadata">General metadata for the <see cref="AIAgent"/> t</param>
    public static IAIAgentHostingBuilder WithDiscovery(this IAIAgentHostingBuilder builder, GeneralMetadata? generalMetadata = null)
    {
        var agentDiscovery = InitializeAgentsDiscoveryProvider(builder.Services);
        generalMetadata ??= builder.ResolveMetadata();

        agentDiscovery.RegisterAgentDiscovery(builder.ActorType, generalMetadata!);

        return builder;
    }

    /// <summary>
    /// Adds <see cref="AIAgent"/> to the discovery services exposing the agent metadata via discovery endpoints.
    /// </summary>
    /// <param name="builder">The builder for the <see cref="AIAgent"/></param>
    /// <param name="endpointsMetadata">The endpoints metadata.</param>
    public static IAIAgentHostingBuilder WithEndpoints(this IAIAgentHostingBuilder builder, EndpointsMetadata? endpointsMetadata = null)
    {
        var agentDiscovery = InitializeAgentsDiscoveryProvider(builder.Services);
        agentDiscovery.IncludeEndpoints(builder.ActorType, endpointsMetadata);

        return builder;
    }

    private static GeneralMetadata ResolveMetadata(this IAIAgentHostingBuilder builder) => builder switch
    {
        ChatClientAgentHostingBuilder clientAgentBuilder => new GeneralMetadata
        {
            Name = clientAgentBuilder.ActorType.Name,
            Description = clientAgentBuilder.Description,
            Instructions = clientAgentBuilder.Instructions,
        },
        _ => new GeneralMetadata
        {
            Name = builder.ActorType.Name
        }
    };

    private static AgentDiscovery InitializeAgentsDiscoveryProvider(IServiceCollection services)
    {
        Microsoft.Shared.Diagnostics.Throw.IfNull(services);

        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is AgentDiscovery);
        if (descriptor?.ImplementationInstance is not AgentDiscovery instance)
        {
            instance = new AgentDiscovery(services);
            services.Add(ServiceDescriptor.Singleton(instance));
            // instance.ConfigureServices(services);
        }

        return instance;
    }
}
