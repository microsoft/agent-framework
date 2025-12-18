// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostedWorkflowBuilder : IHostedWorkflowBuilder
{
    public string Name { get; }
    public IServiceCollection Services { get; }

    public HostedWorkflowBuilder(string name, IHostApplicationBuilder builder)
        : this(name, builder.Services)
    {
    }

    public HostedWorkflowBuilder(string name, IServiceCollection services)
    {
        this.Name = name;
        this.Services = services;
    }
}
