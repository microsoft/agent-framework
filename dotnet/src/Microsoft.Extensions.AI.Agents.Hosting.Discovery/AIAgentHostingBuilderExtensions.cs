// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Extensions for <see cref="IAIAgentHostingBuilder"/>
/// </summary>
public static class AIAgentHostingBuilderExtensions
{
    public static IAIAgentHostingBuilder WithDiscovery(IAIAgentHostingBuilder agentHostingBuilder)
    {
        var agentDiscovery = InitializeAgentsDiscoveryProvider(agentHostingBuilder.Services);
        agentDiscovery.RegisterAgent(agentHostingBuilder.);
    }

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
