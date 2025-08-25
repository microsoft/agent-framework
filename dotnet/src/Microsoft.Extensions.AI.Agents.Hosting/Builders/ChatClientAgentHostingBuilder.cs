// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Builders;

internal class ChatClientAgentHostingBuilder : IAIAgentHostingBuilder
{
    public IServiceCollection Services { get; }
    public ActorType ActorType { get; }
    public string Instructions { get; }
    public string? Description { get; }

    public ChatClientAgentHostingBuilder(IServiceCollection services, string name, string instructions, string? description = null)
    {
        this.Services = services;
        this.ActorType = new ActorType(name);
        this.Instructions = instructions;
        this.Description = description;
    }
}
