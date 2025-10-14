// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class HostedWorkflowBuilder : IHostedWorkflowBuilder
{
    public string Name { get; }
    public IHostApplicationBuilder HostApplicationBuilder { get; }

    public HostedWorkflowBuilder(string name, IHostApplicationBuilder hostApplicationBuilder)
    {
        this.Name = name;
        this.HostApplicationBuilder = hostApplicationBuilder;
    }
}
