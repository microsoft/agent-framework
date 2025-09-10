// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Actor;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
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
    public static IAgentHostingBuilder WithDiscovery(this IAgentHostingBuilder builder)
    {
        var agentDiscovery = builder.Services.InitializeAgentsDiscoveryProvider();
        builder.Services.InitializeHttpActorProcessor();

        var actorType = builder.ActorType;
        agentDiscovery.RegisterAgentDiscovery(actorType);

        return builder;
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

    internal static void InitializeHttpActorProcessor(this IServiceCollection services)
    {
        Throw.IfNull(services);

        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is HttpActorProcessor);
        if (descriptor?.ImplementationInstance is not HttpActorProcessor instance)
        {
            services.AddSingleton<HttpActorProcessor>();
        }
    }
}
