// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostedAgentBuilder : IHostedAgentBuilder
{
    public string Name { get; }
    public IServiceCollection ServiceCollection { get; }

    public HostedAgentBuilder(string name, IHostApplicationBuilder builder)
        : this(name, builder.Services)
    {
    }

    public HostedAgentBuilder(string name, IServiceCollection serviceCollection)
    {
        this.Name = name;
        this.ServiceCollection = serviceCollection;
    }
}
