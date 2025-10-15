// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.Local;

// Implementation of an AgentCatalog which enumerates agents registered in the local service provider.
internal sealed class LocalAgentCatalog : AgentCatalog
{
    public readonly HashSet<string> _registeredAgents;
    private readonly IServiceProvider _serviceProvider;

    public LocalAgentCatalog(LocalAgentRegistry agentHostBuilder, IServiceProvider serviceProvider)
    {
        this._registeredAgents = [.. agentHostBuilder.AgentNames];
        this._serviceProvider = serviceProvider;
    }

    public override async IAsyncEnumerable<AIAgent> GetAgentsAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.CompletedTask.ConfigureAwait(false);

        foreach (var name in this._registeredAgents)
        {
            var agent = this._serviceProvider.GetKeyedService<AIAgent>(name);
            if (agent is not null)
            {
                yield return agent;
            }
        }
    }
}
