// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Builders;

internal class AIAgentHostingBuilder : IAIAgentHostingBuilder
{
    public IServiceCollection Services { get; }

    public ActorType ActorType { get; }

    public AIAgentHostingBuilder(IServiceCollection services, ActorType actorType)
    {
        this.Services = services;
        this.ActorType = actorType;
    }

    public AIAgentHostingBuilder(IServiceCollection services, string name)
        : this(services, new ActorType(name))
    {
    }
}
