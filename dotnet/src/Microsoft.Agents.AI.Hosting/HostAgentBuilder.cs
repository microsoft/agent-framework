// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostAgentBuilder : IHostAgentBuilder
{
    public string Name { get; }
    public IHostApplicationBuilder HostApplicationBuilder { get; }

    public HostAgentBuilder(string name, IHostApplicationBuilder hostApplicationBuilder)
    {
        this.Name = name;
        this.HostApplicationBuilder = hostApplicationBuilder;
    }
}
