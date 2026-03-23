// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostedAgentBuilder : IHostedAgentBuilder
{
    public string Name { get; }
    public IServiceCollection ServiceCollection { get; }
    public ServiceLifetime Lifetime { get; }

    public HostedAgentBuilder(string name, IHostApplicationBuilder builder, ServiceLifetime lifetime = ServiceLifetime.Singleton)
        : this(name, builder.Services, lifetime)
    {
    }

    public HostedAgentBuilder(string name, IServiceCollection serviceCollection, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        this.Name = name;
        this.ServiceCollection = serviceCollection;
        this.Lifetime = lifetime;
    }
}
