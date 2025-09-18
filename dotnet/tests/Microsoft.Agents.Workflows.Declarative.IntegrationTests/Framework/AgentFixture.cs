// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Shared.IntegrationTests;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

public sealed class AgentFixture : IDisposable
{
    private static IReadOnlyDictionary<string, string?>? s_agentMap;

    internal async Task<IReadOnlyDictionary<string, string?>> GetAgentsAsync(AzureAIConfiguration config, CancellationToken cancellationToken = default)
    {
        s_agentMap ??= await AgentFactory.CreateAsync("Agents", config, cancellationToken);

        return s_agentMap;
    }

    public void Dispose()
    {
        GC.SuppressFinalize(this);
    }
}
