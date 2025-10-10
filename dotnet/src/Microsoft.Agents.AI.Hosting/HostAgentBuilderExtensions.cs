// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

internal static class HostAgentBuilderExtensions
{
    public static IHostAgentBuilder WithThreadStore(this IHostAgentBuilder builder, IAgentThreadStore store)
    {
        builder.HostApplicationBuilder.Services.AddKeyedSingleton(builder.Name, store);
        return builder;
    }
}
