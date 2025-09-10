// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Actor;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
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
    /// <param name="agentMetadata"></param>
    public static IAgentHostingBuilder WithDiscovery(this IAgentHostingBuilder builder, AgentMetadata? agentMetadata = null)
    {
        var agentDiscovery = builder.Services.InitializeAgentsDiscoveryProvider();

        var metadata = agentMetadata ?? builder.ResolveAgentMetadata();
        agentDiscovery.RegisterAgentDiscovery(builder.ActorType, metadata);

        return builder;
    }

    internal static AgentDiscoveryProvider InitializeAgentsDiscoveryProvider(this IServiceCollection services)
    {
        Throw.IfNull(services);

        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is AgentDiscoveryProvider);
        if (descriptor?.ImplementationInstance is not AgentDiscoveryProvider instance)
        {
            instance = new AgentDiscoveryProvider();
            services.Add(ServiceDescriptor.Singleton(instance));
        }

        services.TryAddSingleton<HttpActorProcessor>();

        return instance;
    }
}
