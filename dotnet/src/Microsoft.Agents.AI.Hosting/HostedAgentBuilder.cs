// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostedAgentBuilder : IHostedAgentBuilder
{
    public string Name { get; }
    public IHostApplicationBuilder HostApplicationBuilder { get; }

    public HostedAgentBuilder(string name, IHostApplicationBuilder hostApplicationBuilder)
    {
        this.Name = name;
        this.HostApplicationBuilder = hostApplicationBuilder;
    }
}
